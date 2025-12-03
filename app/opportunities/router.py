"""Opportunity routes - both API and UI endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app.core.base_schemas import ListResponse
from app.core.context import ContextDep, handle_form_error, render_template, require_role, ui_auth_required
from app.db.models import User
from app.opportunities.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatusUpdate,
    OpportunityCreate,
    OpportunityResponse,
)
from app.opportunities.service import ApplicationService, OpportunityService
from app.organizations.service import OrganizationService

# API routes (JSON)
api_router = APIRouter(prefix="/api/opportunities", tags=["Opportunities"])
app_api_router = APIRouter(prefix="/api/applications", tags=["Applications"])

# UI routes (HTML forms)
ui_router = APIRouter(prefix="/opp", tags=["Opportunities UI"])


@api_router.get("", response_model=ListResponse[OpportunityResponse])
async def list_opportunities(ctx: ContextDep) -> ListResponse[OpportunityResponse]:
    """List all open opportunities."""
    ctx.require_authenticated()
    opp_svc = OpportunityService(ctx.db)
    opportunities = await opp_svc.list_open()
    return ListResponse[OpportunityResponse](
        items=[OpportunityResponse.model_validate(opp) for opp in opportunities],
    )


@api_router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(data: OpportunityCreate, ctx: ContextDep) -> OpportunityResponse:
    """Create a new opportunity (organization role only)."""
    user = ctx.require_authenticated()
    require_role(user, "organization", "create opportunities")

    # Verify user is member of organization
    org_svc = OrganizationService(ctx.db)
    await org_svc.get_by_id(data.organization_id)
    await org_svc.require_member(user.id, data.organization_id)

    # Create opportunity
    opp_svc = OpportunityService(ctx.db)
    opportunity = await opp_svc.create(
        title=data.title,
        description=data.description,
        organization_id=data.organization_id,
        posted_by=user.id,
        location=data.location,
    )
    return OpportunityResponse.model_validate(opportunity)


@api_router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(opportunity_id: UUID, ctx: ContextDep) -> OpportunityResponse:
    """Get a single opportunity by ID."""
    ctx.require_authenticated()
    opp_svc = OpportunityService(ctx.db)
    opportunity = await opp_svc.get_by_id(opportunity_id)
    return OpportunityResponse.model_validate(opportunity)


@api_router.post("/{opportunity_id}/apply", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def apply_to_opportunity(
    opportunity_id: UUID,
    data: ApplicationCreate,
    ctx: ContextDep,
) -> ApplicationResponse:
    """Apply to an opportunity (volunteers only)."""
    user = ctx.require_authenticated()
    require_role(user, "volunteer", "apply to opportunities")

    app_svc = ApplicationService(ctx.db)
    application = await app_svc.apply(
        opportunity_id=opportunity_id,
        volunteer_id=user.id,
        message=data.message,
    )
    return ApplicationResponse.model_validate(application)


@app_api_router.get("", response_model=ListResponse[ApplicationResponse])
async def list_user_applications(ctx: ContextDep) -> ListResponse[ApplicationResponse]:
    """List all applications for the current user."""
    user = ctx.require_authenticated()
    app_svc = ApplicationService(ctx.db)
    applications = await app_svc.get_by_volunteer(user.id)
    return ListResponse[ApplicationResponse](
        items=[ApplicationResponse.model_validate(app) for app in applications],
    )


@app_api_router.put("/{application_id}/status", response_model=ApplicationResponse)
async def update_application_status(
    application_id: UUID,
    data: ApplicationStatusUpdate,
    ctx: ContextDep,
) -> ApplicationResponse:
    """Update application status (organization admins only)."""
    app_svc = ApplicationService(ctx.db)
    opp_svc = OpportunityService(ctx.db)

    application = await app_svc.get_by_id(application_id)
    opportunity = await opp_svc.get_by_id(application.opportunity_id)

    # Check if user is organization admin
    await ctx.require_organization_admin(opportunity.organization_id)

    application = await app_svc.update_status(application, data.status)
    return ApplicationResponse.model_validate(application)


@app_api_router.delete("/{application_id}/withdraw", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_application(application_id: UUID, ctx: ContextDep) -> None:
    """Withdraw an application (volunteers only)."""
    user = ctx.require_authenticated()
    app_svc = ApplicationService(ctx.db)
    await app_svc.withdraw(application_id, user)


@ui_router.get("/list")
@ui_auth_required
async def list_opportunities_ui(ctx: ContextDep, user: User) -> Response:
    """Shows the opportunities list page."""
    opp_svc = OpportunityService(ctx.db)
    opportunities = await opp_svc.list_open()
    return render_template(ctx.request, "opp_list.html", user=user, opportunities=opportunities)


@ui_router.get("/new")
@ui_auth_required
async def new_opportunity_form(ctx: ContextDep, user: User) -> Response:
    """Shows the create opportunity form (organization only)."""
    require_role(user, "organization", "create opportunities")
    opp_svc = OpportunityService(ctx.db)
    organizations = await opp_svc.get_user_organizations(user.id)
    return render_template(
        ctx.request,
        "opp_form.html",
        user=user,
        organizations=organizations,
    )


@ui_router.post("/new")
@ui_auth_required
async def create_opportunity_form(
    ctx: ContextDep,
    user: User,
    title: Annotated[str, Form(...)],
    description: Annotated[str, Form(...)],
    organization_id: Annotated[UUID, Form(...)],
    location: Annotated[str, Form()] = "",
) -> Response:
    """Creates a new opportunity from form submission."""
    require_role(user, "organization", "create opportunities")

    try:
        org_svc = OrganizationService(ctx.db)
        await org_svc.get_by_id(organization_id)
        await org_svc.require_member(user.id, organization_id)

        opp_svc = OpportunityService(ctx.db)
        await opp_svc.create(
            title=title,
            description=description,
            organization_id=organization_id,
            posted_by=user.id,
            location=location if location else None,
        )
        return RedirectResponse(url="/opp/list", status_code=303)
    except HTTPException as e:
        return handle_form_error(ctx.request, "opp_form.html", e)


@ui_router.get("/{opportunity_id}")
@ui_auth_required
async def view_opportunity(ctx: ContextDep, user: User, opportunity_id: UUID) -> Response:
    """Shows a single opportunity detail page."""
    opp_svc = OpportunityService(ctx.db)
    app_svc = ApplicationService(ctx.db)

    opportunity = await opp_svc.get_by_id(opportunity_id)

    # Check if user has already applied (for volunteers)
    user_application = None
    if user.role == "volunteer":
        user_application = await app_svc.check_already_applied(user.id, opportunity_id)

    # Check if user is organization admin
    is_admin = False
    if user.role == "organization":
        is_admin = await app_svc.is_organization_admin(user.id, opportunity.organization_id)

    return render_template(
        ctx.request,
        "opp_detail.html",
        user=user,
        opportunity=opportunity,
        user_application=user_application,
        is_admin=is_admin,
    )


@ui_router.get("/{opportunity_id}/apply")
@ui_auth_required
async def apply_form(ctx: ContextDep, user: User, opportunity_id: UUID) -> Response:
    """Shows the application form for an opportunity."""
    require_role(user, "volunteer", "apply to opportunities")

    opp_svc = OpportunityService(ctx.db)
    app_svc = ApplicationService(ctx.db)

    opportunity = await opp_svc.get_by_id(opportunity_id)

    # Check if already applied
    if await app_svc.check_already_applied(user.id, opportunity_id):
        return RedirectResponse(url=f"/opp/{opportunity_id}", status_code=303)

    return render_template(
        ctx.request,
        "app_form.html",
        user=user,
        opportunity=opportunity,
    )


@ui_router.post("/{opportunity_id}/apply")
@ui_auth_required
async def submit_application(
    ctx: ContextDep,
    user: User,
    opportunity_id: UUID,
    message: Annotated[str, Form()] = "",
) -> Response:
    """Submits an application for an opportunity."""
    require_role(user, "volunteer", "apply to opportunities")

    opp_svc = OpportunityService(ctx.db)
    app_svc = ApplicationService(ctx.db)

    # Get opportunity first for error handling context
    opportunity = await opp_svc.get_by_id(opportunity_id)

    try:
        await app_svc.apply(
            opportunity_id=opportunity_id,
            volunteer_id=user.id,
            message=message if message else None,
        )
        return RedirectResponse(url=f"/opp/{opportunity_id}", status_code=303)
    except HTTPException as e:
        return handle_form_error(ctx.request, "app_form.html", e, opportunity=opportunity)


@ui_router.get("/applications/list")
@ui_auth_required
async def list_applications_ui(ctx: ContextDep, user: User) -> Response:
    """Shows the user's applications list page."""
    app_svc = ApplicationService(ctx.db)
    applications = await app_svc.get_by_volunteer_with_opportunity(user.id)
    return render_template(
        ctx.request,
        "app_list.html",
        user=user,
        applications=applications,
    )


@ui_router.get("/{opportunity_id}/applicants")
@ui_auth_required
async def view_applicants(ctx: ContextDep, user: User, opportunity_id: UUID) -> Response:
    """Shows the applicants list for an opportunity (organization admins only)."""
    opp_svc = OpportunityService(ctx.db)
    app_svc = ApplicationService(ctx.db)

    opportunity = await opp_svc.get_by_id(opportunity_id)
    await ctx.require_organization_admin(opportunity.organization_id)

    applications = await app_svc.get_by_opportunity_with_volunteer(opportunity_id)
    return render_template(
        ctx.request,
        "applicants_list.html",
        user=user,
        opportunity=opportunity,
        applications=applications,
    )


async def _update_applicant_status(
    ctx: ContextDep,
    opportunity_id: UUID,
    application_id: UUID,
    new_status: str,
) -> Response:
    """Update application status (organization admins only)."""
    result = ctx.require_ui_auth()
    if isinstance(result, RedirectResponse):
        return result

    opp_svc = OpportunityService(ctx.db)
    app_svc = ApplicationService(ctx.db)

    opportunity = await opp_svc.get_by_id(opportunity_id)
    await ctx.require_organization_admin(opportunity.organization_id)

    application = await app_svc.get_by_id(application_id)
    if application.opportunity_id != opportunity_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    await app_svc.update_status(application, new_status)
    return RedirectResponse(url=f"/opp/{opportunity_id}/applicants", status_code=303)


@ui_router.post("/{opportunity_id}/applicants/{application_id}/accept")
async def accept_applicant(ctx: ContextDep, opportunity_id: UUID, application_id: UUID) -> Response:
    """Accept an application (organization admins only)."""
    return await _update_applicant_status(ctx, opportunity_id, application_id, "accepted")


@ui_router.post("/{opportunity_id}/applicants/{application_id}/reject")
async def reject_applicant(ctx: ContextDep, opportunity_id: UUID, application_id: UUID) -> Response:
    """Reject an application (organization admins only)."""
    return await _update_applicant_status(ctx, opportunity_id, application_id, "rejected")


@ui_router.post("/applications/{application_id}/withdraw")
async def withdraw_application_ui(ctx: ContextDep, application_id: UUID) -> Response:
    """Withdraw an application (volunteers only)."""
    result = ctx.require_ui_auth()
    if isinstance(result, RedirectResponse):
        return result
    user = result

    app_svc = ApplicationService(ctx.db)
    await app_svc.withdraw(application_id, user)
    return RedirectResponse(url="/opp/applications/list", status_code=303)
