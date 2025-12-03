"""Router for user and organization profiles."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.context import RequestContext, get_context, render_template
from app.db.models import Organization, User
from app.db.repositories import OrganizationRepository, UserRepository

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
        return render_template(ctx.request, "user_profile.html", user=ctx.user, profile_user=user)

    # Check Organization
    org_repo = OrganizationRepository(ctx.db)
    org = await org_repo.find_one(Organization.name == slug)
    if org:
        return render_template(ctx.request, "org_profile_public.html", user=ctx.user, organization=org)

    return ctx.error_response("Profile not found", status_code=404)
