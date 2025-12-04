"""Organization routes - both API and UI endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app.core.base_schemas import ListResponse, error_responses, list_response
from app.core.context import (
    ContextDep,
    handle_form_error,
    render_template,
    require_organization_role,
    ui_auth_required,
)
from app.core.dependencies import OrganizationServiceDep
from app.db.models import User
from app.organizations.schemas import (
    OrganizationCreate,
    OrganizationDetailResponse,
    OrganizationResponse,
    OrganizationUpdate,
)

# API routes (JSON)
api_router = APIRouter(prefix="/api/organizations", tags=["Organizations"])

# UI routes (HTML forms) - excluded from OpenAPI schema
ui_router = APIRouter(prefix="/org", tags=["Organizations UI"], include_in_schema=False)


@api_router.get("", response_model=ListResponse[OrganizationResponse], responses=error_responses(auth=True))
async def list_organizations(ctx: ContextDep, org_svc: OrganizationServiceDep) -> ListResponse[OrganizationResponse]:
    """List all organizations."""
    ctx.require_authenticated()
    organizations = await org_svc.list_all()
    return list_response(organizations, OrganizationResponse)


@api_router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(auth=True, forbidden=True),
)
async def create_organization(
    data: OrganizationCreate,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> OrganizationResponse:
    """Create a new organization (organization role only).

    The creator is automatically assigned as organization admin.
    """
    user = ctx.require_authenticated()
    require_organization_role(user)
    organization = await org_svc.create(name=data.name, description=data.description, admin_user_id=user.id)
    return OrganizationResponse.model_validate(organization)


@api_router.get(
    "/{organization_id}",
    response_model=OrganizationDetailResponse,
    responses=error_responses(auth=True, not_found=True),
)
async def get_organization(
    organization_id: UUID,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> OrganizationDetailResponse:
    """Get a single organization by ID with member details."""
    ctx.require_authenticated()

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


@api_router.put(
    "/{organization_id}",
    response_model=OrganizationResponse,
    responses=error_responses(auth=True, forbidden=True, not_found=True),
)
async def update_organization(
    organization_id: UUID,
    data: OrganizationUpdate,
    ctx: ContextDep,
    org_svc: OrganizationServiceDep,
) -> OrganizationResponse:
    """Update an organization (organization admins only)."""
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(ctx.require_authenticated().id, organization_id)

    organization = await org_svc.update(organization, name=data.name, description=data.description)
    return OrganizationResponse.model_validate(organization)


@ui_router.get("/list")
@ui_auth_required
async def list_organizations_ui(ctx: ContextDep, user: User, org_svc: OrganizationServiceDep) -> Response:
    """Shows the organizations list page."""
    organizations = await org_svc.list_all()
    return render_template(
        ctx.request,
        "org_list.html",
        user=user,
        organizations=organizations,
    )


@ui_router.get("/new")
@ui_auth_required
async def new_organization_form(ctx: ContextDep, user: User) -> Response:
    """Shows the create organization form (organization role only)."""
    require_organization_role(user)
    return render_template(
        ctx.request,
        "org_form.html",
        user=user,
    )


@ui_router.post("/new")
@ui_auth_required
async def create_organization_form(
    ctx: ContextDep,
    user: User,
    org_svc: OrganizationServiceDep,
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
) -> Response:
    """Creates a new organization from form submission (organization role only)."""
    require_organization_role(user)
    try:
        organization = await org_svc.create(
            name=name,
            description=description if description else None,
            admin_user_id=user.id,
        )
        return RedirectResponse(url=f"/org/{organization.id}", status_code=303)
    except HTTPException as e:
        return handle_form_error(ctx.request, "org_form.html", e)


@ui_router.get("/{organization_id}")
@ui_auth_required
async def view_organization(
    ctx: ContextDep, user: User, org_svc: OrganizationServiceDep, organization_id: UUID
) -> Response:
    """Shows a single organization detail page."""
    organization = await org_svc.get_by_id_with_opportunities(organization_id)
    members = await org_svc.get_members(organization_id)
    is_admin = await org_svc.is_admin(user.id, organization_id)

    return render_template(
        ctx.request,
        "org_detail.html",
        user=user,
        organization=organization,
        members=members,
        is_admin=is_admin,
    )


@ui_router.get("/{organization_id}/edit")
@ui_auth_required
async def edit_organization_form(
    ctx: ContextDep, user: User, org_svc: OrganizationServiceDep, organization_id: UUID
) -> Response:
    """Shows the edit organization form (admins only)."""
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(user.id, organization_id)

    return render_template(
        ctx.request,
        "org_form.html",
        user=user,
        organization=organization,
    )


@ui_router.post("/{organization_id}/edit")
@ui_auth_required
async def update_organization_form(
    ctx: ContextDep,
    user: User,
    org_svc: OrganizationServiceDep,
    organization_id: UUID,
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
) -> Response:
    """Updates an organization from form submission."""
    organization = await org_svc.get_by_id(organization_id)
    await org_svc.require_admin(user.id, organization_id)

    try:
        await org_svc.update(
            organization,
            name=name,
            description=description if description else None,
        )
        return RedirectResponse(url=f"/org/{organization.id}", status_code=303)
    except HTTPException as e:
        return handle_form_error(ctx.request, "org_form.html", e, organization=organization)
