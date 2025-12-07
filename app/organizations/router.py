"""Organization routes - both API and UI endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Response, status

from app.core.base_schemas import ListResponse, error_responses
from app.core.context import (
    ContextDep,
    render_template,
    require_organization_role,
)
from app.core.dependencies import OrganizationServiceDep
from app.core.router_helpers import handle_htmx_redirect
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
            template="pages/shared.html",
            view="list",
            block="resource_cards" if ctx.is_htmx else None,
            # Resource list context
            resource_type="organization",
            items=organizations,
            page_title="Organizations",
            create_url="/organizations/new",
            create_text="Create Organization",
            create_color="blue",
            show_create=ctx.user is not None and ctx.user.role == "organization" and len(organizations) > 0,
            empty_message="No organizations found",
            grid_cols="md:grid-cols-2 lg:grid-cols-3",
        )

    return ListResponse[OrganizationResponse](items=[OrganizationResponse.model_validate(org) for org in organizations])


@router.get("/organizations/new", responses=error_responses(auth=True))
async def new_organization_form(ctx: ContextDep) -> Response:
    """Shows the create organization form (organization role only)."""
    user = ctx.require_authenticated()
    require_organization_role(user)
    return render_template(
        ctx.request,
        "pages/shared.html",
        view="form",
        user=user,
        # Resource form context
        resource_type="organization",
        resource=None,
        form_action="/organizations",
        back_url="/organizations",
        form_title="Create New Organization",
        page_title="Organizations",
        submit_text="Create Organization",
        submit_color="blue",
        show_warning=False,
        form_fields=[
            {
                "name": "name",
                "label": "Organization Name",
                "type": "text",
                "placeholder": "Enter organization name",
                "required": True,
                "value": "",
            },
            {
                "name": "description",
                "label": "Description",
                "type": "textarea",
                "placeholder": "Describe your organization, its mission, and goals",
                "required": False,
                "value": "",
                "rows": 6,
            },
        ],
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
            return ctx.error_response(e, template="pages/shared.html", view="form", block="form_content")
        raise

    organization = await org_svc.create(name=data.name, description=data.description, admin_user_id=user.id)

    if ctx.is_ui:
        return handle_htmx_redirect(ctx, f"/organizations/{organization.id}")

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
            template="pages/organizations.html",
            block="org_detail" if ctx.is_htmx else None,
            organization=organization,
            members=members,
            is_admin=is_admin,
            is_public_view=False,
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
        "pages/shared.html",
        view="form",
        user=user,
        # Resource form context
        resource_type="organization",
        resource=organization,
        form_action=f"/organizations/{organization.id}/edit",
        back_url="/organizations",
        form_title="Edit Organization",
        page_title="Organizations",
        submit_text="Update Organization",
        submit_color="blue",
        show_warning=False,
        form_fields=[
            {
                "name": "name",
                "label": "Organization Name",
                "type": "text",
                "placeholder": "Enter organization name",
                "required": True,
                "value": organization.name,
            },
            {
                "name": "description",
                "label": "Description",
                "type": "textarea",
                "placeholder": "Describe your organization, its mission, and goals",
                "required": False,
                "value": organization.description or "",
                "rows": 6,
            },
        ],
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
        return handle_htmx_redirect(ctx, f"/organizations/{organization.id}")
    except HTTPException as e:
        return ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", organization=organization
        )
