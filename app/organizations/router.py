"""Organization routes (UI-only)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from app.core.context import (
    ContextDep,
    render_template,
)
from app.core.context_types import form_view_context, list_view_context
from app.core.dependencies import ImageServiceDep, OrganizationServiceDep
from app.core.form_fields import ORGANIZATION_EDIT_FIELDS, with_values
from app.core.htmx import handle_htmx_redirect
from app.core.services.images import ImagePreset
from app.core.types import UI_RESPONSES
from app.db.models import Organization
from app.organizations.schemas import OrganizationCreate

router = APIRouter(
    tags=["Organizations"],
    default_response_class=HTMLResponse,
    responses=UI_RESPONSES,
)


async def _render_organization_detail(
    ctx: ContextDep,
    org: Organization,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Shared helper for rendering organization detail page.

    Used by both the ID route (/organizations/{id}) and slug route (/{slug}).
    """
    members = await org_svc.get_members(org.id)
    is_admin = False
    if ctx.user:
        is_admin = await org_svc.is_admin(ctx.user.id, org.id)

    return await ctx.success_response(
        template="pages/organizations.html",
        organization=org,
        members=members,
        is_admin=is_admin,
        is_public_view=False,
    )


@router.get("/organizations")
async def list_organizations(
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
    page: int = 1,
) -> Response:
    """List all organizations."""
    ctx.require_authenticated()
    limit = 9

    items, total = await org_svc.list_all(page=page, limit=limit)

    context = list_view_context(
        items=items,
        page_title="Organizations",
        meta={"page": page, "total": total, "per_page": limit, "total_pages": (total + limit - 1) // limit},
        show_create=ctx.user is not None,
        empty_message="No organizations found",
    )
    return await ctx.success_response(template="pages/organizations/list.html", **context)


@router.post("/organizations")
async def create_organization(
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Create a new organization."""
    user = ctx.require_authenticated()

    try:
        data = await ctx.parse_body_or_400(
            OrganizationCreate,
            {
                "name": "name",
                "username": "username",
                "description": "description",
            },
        )
    except HTTPException as e:
        if ctx.is_htmx:
            return await ctx.error_response(e, template=None, block=None)
        return await ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", page_title="Organizations"
        )

    try:
        organization = await org_svc.create(
            name=data.name,
            username=data.username,
            description=data.description,
            admin_user_id=user.id,
        )
    except HTTPException as e:
        if ctx.is_htmx:
            return await ctx.error_response(e, template=None, block=None)
        return await ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", page_title="Organizations"
        )

    return await handle_htmx_redirect(ctx, f"/{organization.username}")


@router.get("/organizations/{organization_id}")
async def get_organization(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Get a single organization by ID."""
    ctx.require_authenticated()

    organization = await org_svc.get_by_id_with_opportunities(organization_id)
    return await _render_organization_detail(ctx, organization, org_svc)


@router.put("/organizations/{organization_id}")
async def update_organization(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
) -> Response:
    """Update an organization."""
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(ctx.require_authenticated().id, organization_id)

    await org_svc.update(organization, name=name, description=description if description else None)
    return await handle_htmx_redirect(ctx, f"/{organization.username}")


@router.get("/organizations/{organization_id}/edit")
async def edit_organization_form(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Show edit organization form."""
    user = ctx.require_authenticated()
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(user.id, organization_id)

    fields = with_values(
        ORGANIZATION_EDIT_FIELDS,
        {"name": organization.name, "description": organization.description or ""},
    )
    context = form_view_context(
        resource_type="organization",
        form_action=f"/organizations/{organization.id}/edit",
        back_url="/organizations",
        form_title="Edit Organization",
        page_title="Organizations",
        form_fields=fields,
        resource=organization,
        submit_text="Update Organization",
        submit_color="blue",
    )
    return await render_template(ctx.request, "pages/shared.html", user=user, **context)


@router.post("/organizations/{organization_id}/edit")
async def update_organization_form(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
) -> Response:
    """Update organization from form submission."""
    user = ctx.require_authenticated()
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(user.id, organization_id)

    try:
        await org_svc.update(
            organization,
            name=name,
            description=description if description else None,
        )
        return await handle_htmx_redirect(ctx, f"/{organization.username}")
    except HTTPException as e:
        return await ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", organization=organization
        )


@router.post("/organizations/{organization_id}/banner")
async def upload_organization_banner(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
    image_svc: ImageServiceDep,
    file: Annotated[UploadFile, File(...)],
) -> Response:
    """Upload organization banner image."""
    user = ctx.require_authenticated()
    await org_svc.require_admin(user.id, organization_id)

    content = await file.read()
    org = await org_svc.get_by_id(organization_id)

    filename = await run_in_threadpool(
        image_svc.process_and_save,
        content,
        organization_id,
        ImagePreset.BANNER,
    )
    await org_svc.update_banner(organization_id, filename)
    return await handle_htmx_redirect(ctx, f"/{org.username}")


@router.post("/organizations/{organization_id}/logo")
async def upload_organization_logo(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
    image_svc: ImageServiceDep,
    file: Annotated[UploadFile, File(...)],
) -> Response:
    """Upload organization logo image."""
    user = ctx.require_authenticated()
    await org_svc.require_admin(user.id, organization_id)

    content = await file.read()
    org = await org_svc.get_by_id(organization_id)

    filename = await run_in_threadpool(
        image_svc.process_and_save,
        content,
        organization_id,
        ImagePreset.LOGO,
    )
    await org_svc.update_logo(organization_id, filename)
    return await handle_htmx_redirect(ctx, f"/{org.username}")


@router.delete("/organizations/{organization_id}")
async def delete_organization(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Soft-delete an organization (admins only)."""
    user = ctx.require_authenticated()
    await org_svc.require_admin(user.id, organization_id)
    await org_svc.soft_delete(organization_id)
    return await handle_htmx_redirect(ctx, "/organizations")


@router.post("/organizations/{organization_id}/delete", include_in_schema=False)
async def delete_organization_post(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Soft-delete an organization via UI POST (admins only)."""
    user = ctx.require_authenticated()
    await org_svc.require_admin(user.id, organization_id)
    await org_svc.soft_delete(organization_id)
    return await handle_htmx_redirect(ctx, "/organizations")
