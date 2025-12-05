"""Opportunity routes - both API and UI endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from app.core.base_schemas import ListResponse, error_responses
from app.core.context import (
    ContextDep,
    render_template,
    require_organization_role,
    require_volunteer_role,
)
from app.core.dependencies import (
    ApplicationServiceDep,
    OpportunityServiceDep,
    OrganizationServiceDep,
)
from app.core.htmx import htmx_redirect
from app.opportunities.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatusUpdate,
    OpportunityCreate,
    OpportunityResponse,
)

# Unified router
router = APIRouter(tags=["Opportunities"])


@router.get("/opportunities", response_model=None, responses=error_responses(auth=True))
async def list_opportunities(ctx: ContextDep, opp_svc: OpportunityServiceDep) -> Response:
    """List all open opportunities."""
    # Optional auth for list? The original UI list required auth, API did too.
    # Let's keep it authenticated for now as per original code.
    ctx.require_authenticated()
    opportunities = await opp_svc.list_open()

    return ctx.success_response(
        data=ListResponse[OpportunityResponse](
            items=[OpportunityResponse.model_validate(opp) for opp in opportunities]
        ),
        template="opp_list.html",
        block="opportunity_cards" if ctx.is_htmx else None,
        opportunities=opportunities,
    )


@router.get("/opportunities/new", response_model=None, responses=error_responses(auth=True))
async def new_opportunity_form(ctx: ContextDep, opp_svc: OpportunityServiceDep) -> Response:
    """Shows the create opportunity form (organization only)."""
    user = ctx.require_authenticated()
    require_organization_role(user)
    organizations = await opp_svc.get_user_organizations(user.id)
    return render_template(
        ctx.request,
        "opp_form.html",
        user=user,
        organizations=organizations,
    )


@router.post(
    "/opportunities",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(auth=True),
)
async def create_opportunity(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Create a new opportunity (organization role only)."""
    user = ctx.require_authenticated()
    require_organization_role(user)

    # Parse body (supports JSON and Form)
    data = await ctx.parse_body_or_400(
        OpportunityCreate,
        {"title": "title", "description": "description", "organization_id": "organization_id", "location": "location"},
    )

    # Verify user is member of organization
    await org_svc.get_by_id(data.organization_id)
    await org_svc.require_member(user.id, data.organization_id)

    try:
        opportunity = await opp_svc.create(
            title=data.title,
            description=data.description,
            organization_id=data.organization_id,
            posted_by=user.id,
            location=data.location,
        )

        if ctx.is_ui:
            if ctx.is_htmx:
                return htmx_redirect("/opportunities")
            return RedirectResponse(url="/opportunities", status_code=303)

        return ctx.success_response(data=OpportunityResponse.model_validate(opportunity), status_code=201)
    except HTTPException as e:
        return ctx.error_response(e, template="opp_form.html", block="form_content")


@router.get(
    "/opportunities/{opportunity_id}", response_model=None, responses=error_responses(auth=True, not_found=True)
)
async def get_opportunity(
    opportunity_id: UUID,
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    app_svc: ApplicationServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Get a single opportunity by ID."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id(opportunity_id)

    if ctx.is_ui:
        # Check if user has already applied (for volunteers)
        user_application = None
        if user.role == "volunteer":
            user_application = await app_svc.check_already_applied(user.id, opportunity_id)

        # Check if user is organization admin
        is_admin = False
        if user.role == "organization":
            is_admin = await org_svc.is_admin(user.id, opportunity.organization_id)

        return ctx.success_response(
            template="opp_detail.html",
            block="opp_detail" if ctx.is_htmx else None,
            opportunity=opportunity,
            user_application=user_application,
            is_admin=is_admin,
        )

    return ctx.success_response(data=OpportunityResponse.model_validate(opportunity))


@router.get("/opportunities/{opportunity_id}/apply", response_model=None, responses=error_responses(auth=True))
async def apply_form(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    app_svc: ApplicationServiceDep,
    opportunity_id: UUID,
) -> Response:
    """Shows the application form for an opportunity."""
    user = ctx.require_authenticated()
    require_volunteer_role(user)

    opportunity = await opp_svc.get_by_id(opportunity_id)

    # Check if already applied
    if await app_svc.check_already_applied(user.id, opportunity_id):
        return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)

    return render_template(
        ctx.request,
        "app_form.html",
        user=user,
        opportunity=opportunity,
    )


@router.post(
    "/opportunities/{opportunity_id}/apply",
    response_model=None,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(auth=True, forbidden=True, not_found=True, conflict=True),
)
async def apply_to_opportunity(
    opportunity_id: UUID,
    ctx: ContextDep,
    app_svc: ApplicationServiceDep,
    opp_svc: OpportunityServiceDep,
) -> Response:
    """Apply to an opportunity (volunteers only)."""
    user = ctx.require_authenticated()
    require_volunteer_role(user)

    # Parse body
    data = await ctx.parse_body_or_400(ApplicationCreate, {"message": "message"})

    # Get opportunity first for error handling context (needed for UI)
    if ctx.is_ui:
        opportunity = await opp_svc.get_by_id(opportunity_id)

    try:
        application = await app_svc.apply(
            opportunity_id=opportunity_id,
            volunteer_id=user.id,
            message=data.message,
        )

        if ctx.is_ui:
            if ctx.is_htmx:
                return htmx_redirect(f"/opportunities/{opportunity_id}")
            return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)

        return ctx.success_response(data=ApplicationResponse.model_validate(application), status_code=201)
    except HTTPException as e:
        if ctx.is_ui:
            return ctx.error_response(e, template="app_form.html", block="form_content", opportunity=opportunity)
        raise


@router.get("/applications", response_model=None, responses=error_responses(auth=True))
async def list_user_applications(ctx: ContextDep, app_svc: ApplicationServiceDep) -> Response:
    """List all applications for the current user."""
    user = ctx.require_authenticated()

    if ctx.is_ui:
        applications = await app_svc.get_by_volunteer_with_opportunity(user.id)
        return render_template(
            ctx.request,
            "app_list.html",
            user=user,
            applications=applications,
        )

    applications = await app_svc.get_by_volunteer(user.id)
    return ctx.success_response(
        data=ListResponse[ApplicationResponse](items=[ApplicationResponse.model_validate(app) for app in applications])
    )


@router.put(
    "/applications/{application_id}/status",
    response_model=None,
    responses=error_responses(auth=True, forbidden=True, not_found=True),
)
async def update_application_status(
    application_id: UUID,
    ctx: ContextDep,
    app_svc: ApplicationServiceDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Update application status (organization admins only)."""
    user = ctx.require_authenticated()

    # Parse body
    data = await ctx.parse_body_or_400(ApplicationStatusUpdate, {"status": "status"})

    application = await app_svc.get_by_id(application_id)
    opportunity = await opp_svc.get_by_id(application.opportunity_id)

    # Check if user is organization admin
    await org_svc.require_admin(user.id, opportunity.organization_id)

    application = await app_svc.update_status(application, data.status)

    if ctx.is_ui:
        # Redirect back to applicants list
        return RedirectResponse(url=f"/opportunities/{opportunity.id}/applicants", status_code=303)

    return ctx.success_response(data=ApplicationResponse.model_validate(application))


@router.delete(
    "/applications/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(auth=True, forbidden=True, not_found=True),
)
async def withdraw_application(
    application_id: UUID,
    ctx: ContextDep,
    app_svc: ApplicationServiceDep,
) -> Response:
    """Withdraw an application (volunteers only)."""
    user = ctx.require_authenticated()
    await app_svc.withdraw(application_id, user)
    return Response(status_code=204)


@router.post("/applications/{application_id}/withdraw", include_in_schema=False)
async def withdraw_application_post(
    application_id: UUID,
    ctx: ContextDep,
    app_svc: ApplicationServiceDep,
    opp_svc: OpportunityServiceDep,
) -> Response:
    """Withdraw an application (UI POST alias)."""
    user = ctx.require_authenticated()
    require_volunteer_role(user)
    # Get application details before withdrawing (since it will be deleted)
    application = await app_svc.get_by_id(application_id)
    opportunity = await opp_svc.get_by_id(application.opportunity_id)

    await app_svc.withdraw(application_id, user)

    if ctx.is_htmx:
        # Check target to decide response
        target = ctx.request.headers.get("hx-target", "")
        if target == "application-status-section":
            # We are on detail page, re-render the status section
            return ctx.success_response(
                template="opp_detail.html",
                block="user_application_status",
                opportunity=opportunity,
            )
        # We are on list page, return empty string to remove card
        return Response(content="", media_type="text/html")

    return ctx.success_response(redirect_url="/applications")


# ... imports ...


@router.get("/opportunities/{opportunity_id}/applicants", response_model=None, responses=error_responses(auth=True))
async def view_applicants(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    app_svc: ApplicationServiceDep,
    org_svc: OrganizationServiceDep,
    opportunity_id: UUID,
) -> Response:
    """Shows the applicants list for an opportunity (organization admins only)."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id(opportunity_id)
    await org_svc.require_admin(user.id, opportunity.organization_id)

    applications = await app_svc.get_by_opportunity_with_volunteer(opportunity_id)
    return render_template(
        ctx.request,
        "applicants_list.html",
        user=user,
        opportunity=opportunity,
        applications=applications,
    )


@router.post("/opportunities/{opportunity_id}/applicants/{application_id}/accept", include_in_schema=False)
async def accept_applicant(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    app_svc: ApplicationServiceDep,
    org_svc: OrganizationServiceDep,
    opportunity_id: UUID,
    application_id: UUID,
) -> Response:
    """Accept an application (UI helper)."""
    # Reuse the update logic but fake the body or call service directly
    # Since we have the logic in update_application_status, we could call it,
    # but it expects a request body. Easier to just call service here.
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id(opportunity_id)
    await org_svc.require_admin(user.id, opportunity.organization_id)

    application = await app_svc.get_by_id(application_id)
    if application.opportunity_id != opportunity_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    await app_svc.update_status(application, "accepted")
    return RedirectResponse(url=f"/opportunities/{opportunity_id}/applicants", status_code=303)


@router.post("/opportunities/{opportunity_id}/applicants/{application_id}/reject", include_in_schema=False)
async def reject_applicant(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    app_svc: ApplicationServiceDep,
    org_svc: OrganizationServiceDep,
    opportunity_id: UUID,
    application_id: UUID,
) -> Response:
    """Reject an application (UI helper)."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id(opportunity_id)
    await org_svc.require_admin(user.id, opportunity.organization_id)

    application = await app_svc.get_by_id(application_id)
    if application.opportunity_id != opportunity_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    await app_svc.update_status(application, "rejected")
    return RedirectResponse(url=f"/opportunities/{opportunity_id}/applicants", status_code=303)
