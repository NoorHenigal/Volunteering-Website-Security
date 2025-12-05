"""Router for user and organization profiles."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import selectinload

from app.core.base_schemas import ListResponse, error_responses, request_body_from_model
from app.core.context import ContextDep, render_template, ui_auth_required
from app.core.dependencies import ProfileServiceDep
from app.core.htmx import htmx_redirect, trigger_toast
from app.core.types import ProfileVisibilityType, SlugPath, UsernamePath
from app.db.models import Organization, User
from app.db.repositories import OrganizationRepository, UserRepository
from app.organizations.schemas import OrganizationResponse
from app.profiles.schemas import (
    FollowResponseSchema,
    PrivacySettingsSchema,
    ProfileUpdateSchema,
    PublicProfileSchema,
)
from app.uploads.service import ImageProcessingError, process_profile_picture

router = APIRouter(tags=["Profiles"])


async def _get_follow_list(
    ctx: ContextDep,
    service: ProfileServiceDep,
    username: str,
    list_type: str,
) -> Response:
    """Shared helper for followers/following list endpoints."""
    profiles = await (service.get_followers if list_type == "followers" else service.get_following)(username, ctx.user)

    if ctx.is_ui:
        user_repo = UserRepository(ctx.db)
        profile_user = await user_repo.get_by_username(username)
        return render_template(
            ctx.request,
            "follow_list.html",
            user=ctx.user,
            profiles=profiles,
            username=username,
            profile_user=profile_user,
            list_type=list_type,
        )
    return ctx.success_response(data=ListResponse[PublicProfileSchema](items=profiles))


async def _update_profile_core(ctx: ContextDep, service: ProfileServiceDep, user: User) -> User:
    """Shared logic for profile update endpoints."""
    data = await ctx.parse_body_or_400(ProfileUpdateSchema, {"bio": "bio", "description": "description"})
    return await service.update_profile(user, data)


@router.get("/settings/profile", include_in_schema=False)
@ui_auth_required
async def edit_profile_page(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Show profile edit page."""
    profile = await service.get_profile(user.username, user)
    return render_template(ctx.request, "profile.html", user=user, profile_user=user, profile=profile, edit_mode=True)


@router.get("/settings/privacy", include_in_schema=False)
@ui_auth_required
async def privacy_settings_page(ctx: ContextDep, user: User) -> Response:
    """Show privacy settings page."""
    return render_template(ctx.request, "privacy_settings.html", user=user)


@router.get(
    "/{username}/followers",
    response_model=ListResponse[PublicProfileSchema],
    responses=error_responses(not_found=True),
)
async def get_followers(username: UsernamePath, ctx: ContextDep, service: ProfileServiceDep) -> Response:
    """Get user's followers."""
    return await _get_follow_list(ctx, service, username, "followers")


@router.get(
    "/{username}/following",
    response_model=ListResponse[PublicProfileSchema],
    responses=error_responses(not_found=True),
)
async def get_following(username: UsernamePath, ctx: ContextDep, service: ProfileServiceDep) -> Response:
    """Get users that this user follows."""
    return await _get_follow_list(ctx, service, username, "following")


@router.get(
    "/{slug}",
    response_model=PublicProfileSchema | OrganizationResponse | None,
    responses=error_responses(not_found=True),
)
async def view_profile(slug: SlugPath, ctx: ContextDep, service: ProfileServiceDep) -> Response:
    """Show user or organization profile."""
    # Check User first
    user_repo = UserRepository(ctx.db)
    profile_user = await user_repo.get_by_username(slug)

    if profile_user:
        profile = await service.get_profile(slug, ctx.user)
        if ctx.is_ui:
            return render_template(
                ctx.request, "profile.html", user=ctx.user, profile_user=profile_user, profile=profile
            )
        return JSONResponse(content=profile.model_dump(mode="json"))

    # Check Organization
    org_repo = OrganizationRepository(ctx.db)
    org = await org_repo.find_one(
        Organization.name == slug,
        options=[selectinload(Organization.opportunities)],
    )
    if org:
        if ctx.is_ui:
            return render_template(ctx.request, "org_profile_public.html", user=ctx.user, organization=org)
        return JSONResponse(content=OrganizationResponse.model_validate(org).model_dump(mode="json"))

    return ctx.error_response("Profile not found", status_code=404)


@router.put(
    "/settings/profile",
    response_model=None,
    responses=error_responses(auth=True, bad_request=True),
    openapi_extra=request_body_from_model(ProfileUpdateSchema),
)
@ui_auth_required
async def update_profile_api(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update own profile bio/description (API)."""
    updated = await _update_profile_core(ctx, service, user)
    return JSONResponse(content={"bio": updated.bio, "description": updated.description})


@router.post("/settings/profile", response_model=None, include_in_schema=False)
@ui_auth_required
async def update_profile_form(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update own profile bio/description (UI form)."""
    await _update_profile_core(ctx, service, user)
    if ctx.is_htmx:
        return htmx_redirect(f"/{user.username}")
    return ctx.success_response(redirect_url=f"/{user.username}")


@router.put(
    "/settings/privacy",
    response_model=None,
    responses=error_responses(auth=True, bad_request=True),
    openapi_extra=request_body_from_model(PrivacySettingsSchema),
)
@ui_auth_required
async def update_privacy_api(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update privacy settings (API)."""
    data = await ctx.parse_body_or_400(
        PrivacySettingsSchema,
        {
            "profile_visibility": "profile_visibility",
            "show_email": "show_email",
            "show_organizations": "show_organizations",
            "searchable": "searchable",
        },
    )

    updated = await service.update_privacy_settings(user, data)

    return JSONResponse(
        content={
            "profile_visibility": updated.profile_visibility,
            "show_email": updated.show_email,
            "show_organizations": updated.show_organizations,
            "searchable": updated.searchable,
        }
    )


@router.post("/settings/privacy", response_model=None, include_in_schema=False)
@ui_auth_required
async def update_privacy_form(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update privacy settings (UI form)."""
    # HTML checkboxes send "on" when checked, nothing when unchecked.
    # This differs from JSON booleans, so we handle manually rather than via parse_body().
    form = await ctx.request.form()

    visibility_raw = form.get("profile_visibility")
    visibility: ProfileVisibilityType | None = None
    if visibility_raw and str(visibility_raw) in ("public", "authenticated", "followers", "private"):
        visibility = str(visibility_raw)  # type: ignore[assignment]

    data = PrivacySettingsSchema(
        profile_visibility=visibility,
        show_email=form.get("show_email") == "on",
        show_organizations=form.get("show_organizations") == "on",
        searchable=form.get("searchable") == "on",
    )

    await service.update_privacy_settings(user, data)

    if ctx.is_htmx:
        # Re-render the form to show updated state (and keep user on page)
        response = ctx.success_response(template="privacy_settings.html", block="content", user=user)
        return trigger_toast(response, "Privacy settings updated")
    return ctx.success_response(redirect_url="/settings/privacy")


@router.post(
    "/{username}/follow",
    response_model=FollowResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={**error_responses(auth=True, not_found=True, conflict=True), 200: {"description": "UI Success"}},
)
@ui_auth_required
async def follow_user(ctx: ContextDep, user: User, service: ProfileServiceDep, username: UsernamePath) -> Response:
    """Follow a user."""
    follow = await service.follow_user(user, username)

    if ctx.is_ui:
        if ctx.is_htmx:
            # Re-render the follow button block
            response = ctx.success_response(
                template="profile.html",
                block="follow_button",
                profile_user=await UserRepository(ctx.db).get_by_username(username),
                profile={"is_following": True},
            )
            return trigger_toast(response, f"You are now following {username}")
        return ctx.success_response(redirect_url=f"/{username}")
    return JSONResponse(content=FollowResponseSchema.model_validate(follow).model_dump(mode="json"), status_code=201)


@router.delete(
    "/{username}/follow",
    response_model=None,
    status_code=204,
    responses={
        **error_responses(auth=True, not_found=True),
        204: {"description": "Successfully unfollowed"},
        200: {"description": "UI Success"},
    },
)
@ui_auth_required
async def unfollow_user_api(
    ctx: ContextDep, user: User, service: ProfileServiceDep, username: UsernamePath
) -> Response:
    """Unfollow a user (API)."""
    await service.unfollow_user(user, username)
    # Return appropriate response based on request type (API vs UI)
    if ctx.is_ui:
        return ctx.success_response(redirect_url=f"/{username}")
    return Response(status_code=204)


@router.post("/{username}/unfollow", response_model=None, include_in_schema=False)
@ui_auth_required
async def unfollow_user_form(
    ctx: ContextDep, user: User, service: ProfileServiceDep, username: UsernamePath
) -> Response:
    """Unfollow a user (UI form)."""
    await service.unfollow_user(user, username)

    if ctx.is_htmx:
        # Re-render the follow button block
        response = ctx.success_response(
            template="profile.html",
            block="follow_button",
            profile_user=await UserRepository(ctx.db).get_by_username(username),
            profile={"is_following": False},
        )
        return trigger_toast(response, f"Unfollowed {username}", "info")

    return ctx.success_response(redirect_url=f"/{username}")


@router.post(
    "/settings/profile/picture",
    response_model=None,
    responses=error_responses(auth=True, bad_request=True),
)
@ui_auth_required
async def upload_profile_picture(
    ctx: ContextDep,
    user: User,
    file: Annotated[UploadFile, File()],
) -> Response:
    """Upload and process profile picture.

    Expects a pre-cropped square image from the client (cropped via Canvas API).
    Re-encodes to WebP, strips metadata, and resizes to 256x256.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    content = await file.read()

    try:
        filename = process_profile_picture(content, user.id)
    except ImageProcessingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    user_repo = UserRepository(ctx.db)
    user.profile_picture = filename
    await user_repo.update(user)

    if ctx.is_ui:
        if ctx.is_htmx:
            return htmx_redirect(f"/{user.username}")
        return ctx.success_response(redirect_url=f"/{user.username}")

    return ctx.success_response(data=None)
