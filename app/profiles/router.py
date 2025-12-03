"""Router for user and organization profiles."""

import contextlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.core.context import RequestContext, get_context, render_template, ui_auth_required
from app.db.models import Organization, User
from app.db.repositories import OrganizationRepository, UserRepository
from app.uploads.service import ImageProcessingError, process_profile_picture

router = APIRouter(tags=["Profiles"])


@router.get("/{slug}")
async def view_profile(
    slug: str,
    ctx: Annotated[RequestContext, Depends(get_context)],
) -> Response:
    """Show user or organization profile."""
    # Check User
    user_repo = UserRepository(ctx.db)
    user = await user_repo.find_one(User.username == slug)
    if user:
        return render_template(ctx.request, "profile.html", user=ctx.user, profile_user=user)

    # Check Organization
    org_repo = OrganizationRepository(ctx.db)
    org = await org_repo.find_one(Organization.name == slug)
    if org:
        return render_template(ctx.request, "org_profile_public.html", user=ctx.user, organization=org)

    return ctx.error_response("Profile not found", status_code=404)


@router.get("/settings/profile")
@ui_auth_required
async def edit_profile_page(
    ctx: Annotated[RequestContext, Depends(get_context)],
    user: User,
) -> Response:
    """Show profile edit page."""
    return render_template(ctx.request, "profile.html", user=user, profile_user=user)


@router.post("/settings/profile/picture")
@ui_auth_required
async def upload_profile_picture(
    ctx: Annotated[RequestContext, Depends(get_context)],
    user: User,
    file: Annotated[UploadFile, File()],
    crop_data: Annotated[str | None, Form()] = None,
) -> Response:
    """Upload and process profile picture.

    Accepts image file with optional crop data as JSON string.
    Re-encodes to WebP, strips metadata, and resizes to 256x256.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    # Read file content
    content = await file.read()

    # Parse crop data if provided
    crop: dict[str, float] | None = None
    if crop_data:
        with contextlib.suppress(json.JSONDecodeError):
            crop = json.loads(crop_data)

    try:
        filename = process_profile_picture(content, user.id, crop_data=crop)
    except ImageProcessingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Update user's profile picture in database
    user_repo = UserRepository(ctx.db)
    user.profile_picture = filename
    await user_repo.update(user)

    # Ensure database changes are committed before redirecting
    await ctx.db.commit()

    if ctx.is_ui:
        return ctx.success_response(redirect_url=f"/{user.username}")

    return ctx.success_response(data=None)
