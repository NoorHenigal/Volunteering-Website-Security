"""Organization routes - both API and UI endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app.core.base_schemas import ListResponse, error_responses
from app.core.context import (
    ContextDep,
    render_template,
    require_organization_role,
)
from app.core.dependencies import OrganizationServiceDep
from app.core.htmx import htmx_redirect
from app.organizations.schemas import (
    OrganizationCreate,
    OrganizationDetailResponse,
    OrganizationResponse,
    OrganizationUpdate,
)

router = APIRouter(tags=["Organizations"])


@router.get(
    "/organizations",
    response_model=ListResponse[OrganizationResponse] | None,
    responses=error_responses(auth=True),
)
async def list_organizations(
    ctx: ContextDep, org_svc: OrganizationServiceDep
) -> Response | ListResponse[OrganizationResponse]:
    """List all organizations."""
    ctx.require_authenticated()
    organizations = await org_svc.list_all()

    if ctx.is_ui:
        return ctx.success_response(
            template="org_list.html",
            block="organization_cards" if ctx.is_htmx else None,
            organizations=organizations,
        )

    return ListResponse[OrganizationResponse](items=[OrganizationResponse.model_validate(org) for org in organizations])


@router.get("/organizations/new", responses=error_responses(auth=True))
async def new_organization_form(ctx: ContextDep) -> Response:
    """Shows the create organization form (organization role only)."""
    user = ctx.require_authenticated()
    require_organization_role(user)
    return render_template(
        ctx.request,
        "org_form.html",
        user=user,
    )


@router.post(
    "/organizations",
    response_model=OrganizationResponse | None,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(auth=True, forbidden=True),
)
async def create_organization(
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response | OrganizationResponse:
    """Create a new organization (organization role only)."""
    user = ctx.require_authenticated()
    require_organization_role(user)

    # Parse body (JSON or Form)
    try:
        data = await ctx.parse_body_or_400(
            OrganizationCreate,
            {"name": "name", "description": "description"},
        )
    except HTTPException as e:
        if ctx.is_ui:
            return ctx.error_response(e, template="org_form.html", block="form_content")
        raise

    organization = await org_svc.create(name=data.name, description=data.description, admin_user_id=user.id)

    if ctx.is_ui:
        if ctx.is_htmx:
            return htmx_redirect(f"/organizations/{organization.id}")
        return RedirectResponse(url=f"/organizations/{organization.id}", status_code=303)

    return OrganizationResponse.model_validate(organization)


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationDetailResponse | None,
    responses=error_responses(auth=True, not_found=True),
)
async def get_organization(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response | OrganizationDetailResponse:
    """Get a single organization by ID."""
    user = ctx.require_authenticated()

    if ctx.is_ui:
        organization = await org_svc.get_by_id_with_opportunities(organization_id)
        members = await org_svc.get_members(organization_id)
        is_admin = await org_svc.is_admin(user.id, organization_id)

        return ctx.success_response(
            template="org_detail.html",
            block="org_detail" if ctx.is_htmx else None,
            organization=organization,
            members=members,
            is_admin=is_admin,
        )

    # API response
    organization = await org_svc.get_by_id(organization_id)
    members = await org_svc.get_members(organization_id)

    return OrganizationDetailResponse(
        id=organization.id,
        name=organization.name,
        description=organization.description,
        members=members,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.put(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    responses=error_responses(auth=True, forbidden=True, not_found=True),
)
async def update_organization(
    organization_id: UUID,
    data: OrganizationUpdate,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> OrganizationResponse:
    """Update an organization (API only)."""
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(ctx.require_authenticated().id, organization_id)

    organization = await org_svc.update(organization, name=data.name, description=data.description)
    return OrganizationResponse.model_validate(organization)


@router.get("/organizations/{organization_id}/edit", responses=error_responses(auth=True))
async def edit_organization_form(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Shows the edit organization form (admins only)."""
    user = ctx.require_authenticated()
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(user.id, organization_id)

    return render_template(
        ctx.request,
        "org_form.html",
        user=user,
        organization=organization,
    )


@router.post("/organizations/{organization_id}/edit")
async def update_organization_form(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
) -> Response:
    """Updates an organization from form submission (UI only)."""
    user = ctx.require_authenticated()
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(user.id, organization_id)

    try:
        await org_svc.update(
            organization,
            name=name,
            description=description if description else None,
        )
        if ctx.is_htmx:
            return htmx_redirect(f"/organizations/{organization.id}")
        return RedirectResponse(url=f"/organizations/{organization.id}", status_code=303)
    except HTTPException as e:
        return ctx.error_response(e, template="org_form.html", block="form_content", organization=organization)
