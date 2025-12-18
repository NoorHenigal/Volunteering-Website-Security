"""Profile routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.core.context import ContextDep, render_template, require_system_admin, ui_auth_required
from app.core.context_types import list_view_context
from app.core.dependencies import ImageServiceDep, OrganizationServiceDep, ProfileServiceDep
from app.core.htmx import handle_htmx_redirect, render_success_page, trigger_toast
from app.core.security import clear_auth_cookies
from app.core.services.images import ImagePreset, ImageProcessingError
from app.core.types import UI_RESPONSES, ProfileVisibilityType, SlugPath, UsernamePath
from app.db.models import Organization, User
from app.db.repositories import OrganizationRepository, UserRepository
from app.organizations.router import _render_organization_detail
from app.profiles.schemas import (
    PrivacySettingsSchema,
    ProfileUpdateSchema,
)

router = APIRouter(
    tags=["Profiles"],
    default_response_class=HTMLResponse,
    responses=UI_RESPONSES,
)


async def _get_follow_list(
    ctx: ContextDep,
    service: ProfileServiceDep,
    username: str,
    list_type: str,
) -> Response:
    """Shared helper for followers/following list endpoints."""
    profiles = await (service.get_followers if list_type == "followers" else service.get_following)(username, ctx.user)

    user_repo = UserRepository(ctx.db)
    profile_user = await user_repo.get_by_username(username)

    title = (
        f"People following {profile_user.first_name if profile_user else username}"
        if list_type == "followers"
        else f"People {profile_user.first_name if profile_user else username} follows"
    )

    context = list_view_context(
        items=profiles,
        page_title=title,
        resource_type=list_type,
        create_url=f"/{username}",
        create_text="Back to profile",
        create_color="blue",
        show_create=False,
        empty_message=f"No {list_type} yet" if list_type == "followers" else "Not following anyone yet",
        grid_cols="space-y-4",
    )

    return await render_template(
        ctx.request,
        "pages/shared.html",
        view="list",
        user=ctx.user,
        profile_user=profile_user,
        **context,
    )


async def _update_profile_core(ctx: ContextDep, service: ProfileServiceDep, user: User) -> User:
    """Shared logic for profile update endpoints."""
    data = await ctx.parse_body_or_400(
        ProfileUpdateSchema,
        {
            "bio": "bio",
            "description": "description",
            "display_name": "display_name",
            "first_name": "first_name",
            "last_name": "last_name",
        },
    )

    return await service.update_profile(user, data)


@router.get("/settings/profile", include_in_schema=False)
@ui_auth_required
async def edit_profile_page(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Show profile edit page."""
    if user.role == "organization":
        org_repo = OrganizationRepository(ctx.db)
        org = await org_repo.find_one(
            Organization.user_roles.any(user_id=user.id, role="admin"),
            Organization.is_active.is_(True),
        )

        return await render_template(
            ctx.request,
            "pages/org_settings.html",
            user=user,
            organization=org,
        )

    profile = await service.get_profile(user.username, user)
    return await render_template(
        ctx.request,
        "pages/profile.html",
        user=user,
        profile_user=user,
        profile=profile,
        edit_mode=True,
    )


@router.get("/settings/privacy", include_in_schema=False)
@ui_auth_required
async def privacy_settings_page(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Show privacy settings page."""
    profile = await service.get_profile(user.username, user)
    return await render_template(
        ctx.request,
        "pages/profile.html",
        view="privacy",
        user=user,
        profile_user=user,
        profile=profile,
    )


@router.delete("/settings/account")
async def delete_account(ctx: ContextDep, service: ProfileServiceDep) -> Response:
    """Deactivate the current user account (soft-delete)."""
    user = ctx.require_authenticated()
    await service.deactivate_user(user)
    response = await handle_htmx_redirect(ctx, "/auth/login")
    clear_auth_cookies(response)
    return response


@router.post("/settings/account/delete", include_in_schema=False)
@ui_auth_required
async def delete_account_post(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Deactivate the current user account via UI POST (soft-delete)."""
    await service.deactivate_user(user)
    response = await handle_htmx_redirect(ctx, "/auth/login")
    clear_auth_cookies(response)
    return response


@router.post("/admin/retention/anonymize")
async def run_retention_anonymization(
    ctx: ContextDep,
    service: ProfileServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Run 90-day retention anonymization for soft-deleted entities (system_admin only)."""
    user = ctx.require_authenticated()
    require_system_admin(user)

    cutoff = datetime.now(UTC) - timedelta(days=90)

    user_result = await ctx.db.execute(select(User).where(User.is_active.is_(False), User.updated_at < cutoff))
    users = list(user_result.scalars().all())
    anonymized_users = 0
    for u in users:
        await service.anonymize_user(u)
        anonymized_users += 1

    org_result = await ctx.db.execute(
        select(Organization).where(Organization.is_active.is_(False), Organization.updated_at < cutoff)
    )
    orgs = list(org_result.scalars().all())
    anonymized_orgs = 0
    for org in orgs:
        await org_svc.anonymize_organization(org)
        anonymized_orgs += 1

    return await render_success_page(
        ctx.request,
        title="Anonymization Complete",
        message="Retention anonymization completed successfully.",
        details={
            "Cutoff Date": cutoff.strftime("%Y-%m-%d %H:%M UTC"),
            "Users Anonymized": str(anonymized_users),
            "Organizations Anonymized": str(anonymized_orgs),
        },
    )


@router.get("/{username}/followers")
async def get_followers(username: UsernamePath, ctx: ContextDep, service: ProfileServiceDep) -> Response:
    """Get user's followers."""
    return await _get_follow_list(ctx, service, username, "followers")


@router.get("/{username}/following")
async def get_following(username: UsernamePath, ctx: ContextDep, service: ProfileServiceDep) -> Response:
    """Get users that this user follows."""
    return await _get_follow_list(ctx, service, username, "following")


@router.get("/{slug}")
async def view_profile(
    slug: SlugPath,
    ctx: ContextDep,
    service: ProfileServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Show user or organization profile."""
    # Check User first
    user_repo = UserRepository(ctx.db)
    profile_user = await user_repo.get_by_username(slug)

    if profile_user and profile_user.role != "organization":
        profile = await service.get_profile(slug, ctx.user)
        return await render_template(
            ctx.request,
            "pages/profile.html",
            user=ctx.user,
            profile_user=profile_user,
            profile=profile,
        )

    # Check Organization
    org_service = org_svc

    # Try to find org by username
    org = await OrganizationRepository(ctx.db).find_one(
        Organization.username == slug,
        options=[selectinload(Organization.opportunities)],
    )

    if org:
        return await _render_organization_detail(ctx, org, org_service)

    return await ctx.error_response("Profile not found", status_code=404)


@router.put("/settings/profile")
@ui_auth_required
async def update_profile_api(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update own profile bio/description."""
    await _update_profile_core(ctx, service, user)
    return await handle_htmx_redirect(ctx, f"/{user.username}")


@router.post("/settings/profile", response_model=None, include_in_schema=False)
@ui_auth_required
async def update_profile_form(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update own profile bio/description (UI form)."""
    await _update_profile_core(ctx, service, user)
    # Use redirect for clean page reload - ensures Alpine.js and navbar work correctly
    return await handle_htmx_redirect(ctx, f"/{user.username}")


@router.put("/settings/privacy")
@ui_auth_required
async def update_privacy_api(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update privacy settings."""
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
        profile = await service.get_profile(user.username, user)
        response = await ctx.success_response(
            template="pages/profile.html",
            view="privacy",
            block="content",
            profile_user=user,
            profile=profile,
        )
        return await trigger_toast(response, "Privacy settings updated")
    return await ctx.success_response(redirect_url="/settings/privacy")


@router.post("/settings/privacy", response_model=None, include_in_schema=False)
@ui_auth_required
async def update_privacy_form(ctx: ContextDep, user: User, service: ProfileServiceDep) -> Response:
    """Update privacy settings (UI form)."""
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
        profile = await service.get_profile(user.username, user)
        response = await ctx.success_response(
            template="pages/profile.html",
            view="privacy",
            block="content",
            profile_user=user,
            profile=profile,
        )
        return await trigger_toast(response, "Privacy settings updated")
    return await ctx.success_response(redirect_url="/settings/privacy")


@router.post("/{username}/follow")
@ui_auth_required
async def follow_user(ctx: ContextDep, user: User, service: ProfileServiceDep, username: UsernamePath) -> Response:
    """Follow a user."""
    await service.follow_user(user, username)

    if ctx.is_htmx:
        response = await ctx.success_response(
            template="pages/profile.html",
            block="follow_button",
            profile_user=await UserRepository(ctx.db).get_by_username(username),
            profile={"is_following": True},
        )
        return await trigger_toast(response, f"You are now following {username}")
    return await ctx.success_response(redirect_url=f"/{username}")


@router.delete("/{username}/follow")
@ui_auth_required
async def unfollow_user_api(
    ctx: ContextDep, user: User, service: ProfileServiceDep, username: UsernamePath
) -> Response:
    """Unfollow a user."""
    await service.unfollow_user(user, username)
    return await ctx.success_response(redirect_url=f"/{username}")


@router.post("/{username}/unfollow", response_model=None, include_in_schema=False)
@ui_auth_required
async def unfollow_user_form(
    ctx: ContextDep, user: User, service: ProfileServiceDep, username: UsernamePath
) -> Response:
    """Unfollow a user (UI form)."""
    await service.unfollow_user(user, username)

    if ctx.is_htmx:
        response = await ctx.success_response(
            template="pages/profile.html",
            block="follow_button",
            profile_user=await UserRepository(ctx.db).get_by_username(username),
            profile={"is_following": False},
        )
        return await trigger_toast(response, f"Unfollowed {username}", "info")

    return await ctx.success_response(redirect_url=f"/{username}")


@router.post("/settings/profile/picture")
@ui_auth_required
async def upload_profile_picture(
    ctx: ContextDep,
    user: User,
    file: Annotated[UploadFile, File()],
    image_svc: ImageServiceDep,
) -> Response:
    """Upload profile picture. Re-encodes to WebP and resizes to 256x256."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    content = await file.read()

    try:
        filename = await run_in_threadpool(
            image_svc.process_and_save, content, user.id, ImagePreset.AVATAR, crop_circular=True
        )
    except ImageProcessingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    user_repo = UserRepository(ctx.db)
    user.profile_picture = filename
    await user_repo.update(user)

    return await handle_htmx_redirect(ctx, f"/{user.username}")
