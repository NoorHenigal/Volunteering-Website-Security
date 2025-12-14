"""Opportunity and application routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.core.base_schemas import ListResponse, PaginationMeta, error_responses
from app.core.context import (
    ContextDep,
    render_template,
    require_volunteer_role,
)
from app.core.context_types import form_view_context, list_view_context
from app.core.dependencies import (
    ApplicationServiceDep,
    ImageServiceDep,
    OpportunityServiceDep,
    OrganizationServiceDep,
)
from app.core.form_fields import OPPORTUNITY_FIELDS, with_select_options
from app.core.htmx import handle_htmx_redirect
from app.core.services.images import ImagePreset
from app.opportunities.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatusUpdate,
    OpportunityCreate,
    OpportunityResponse,
)

router = APIRouter(tags=["Opportunities"])


@router.get("/opportunities", response_model=None, responses=error_responses(auth=True))
async def list_opportunities(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    page: int = 1,
) -> Response:
    """List all open opportunities."""
    ctx.require_authenticated()
    limit = 9

    items, total = await opp_svc.list_open(page=page, limit=limit)

    context = list_view_context(
        items=items,
        page_title="Volunteering Opportunities",
        meta={"page": page, "total": total, "per_page": limit, "total_pages": (total + limit - 1) // limit},
        create_url="/opportunities/new",
        show_create=ctx.user is not None,
        empty_message="No opportunities available at the moment.",
    )

    return await ctx.success_response(
        data=ListResponse[OpportunityResponse](
            items=[OpportunityResponse.model_validate(opp) for opp in items],
            meta=PaginationMeta(total=total, page=page, per_page=limit),
        ),
        template="pages/opportunities/list.html",
        **context,
    )


@router.get("/opportunities/new", response_model=None, responses=error_responses(auth=True))
async def new_opportunity_form(ctx: ContextDep, opp_svc: OpportunityServiceDep) -> Response:
    """Show create opportunity form."""
    user = ctx.require_authenticated()
    organizations = await opp_svc.get_user_organizations(user.id)
    if len(organizations) == 0:
        context = form_view_context(
            resource_type="opportunity",
            form_action="/opportunities",
            back_url="/opportunities",
            form_title="Create New Opportunity",
            page_title="Opportunities",
            form_fields=[],
            submit_text="Create Opportunity",
            submit_color="green",
            show_warning=True,
            warning_title="Organization Required",
            warning_message="You need an organization profile to post opportunities.",
            warning_action_url="/organizations/new",
            warning_action_text="Create Organization",
        )
        return await render_template(ctx.request, "pages/shared.html", user=user, **context)

    fields_with_org = with_select_options(
        OPPORTUNITY_FIELDS,
        "organization_id",
        [(str(org.id), org.name) for org in organizations],
    )
    context = form_view_context(
        resource_type="opportunity",
        form_action="/opportunities",
        back_url="/opportunities",
        form_title="Create New Opportunity",
        page_title="Opportunities",
        form_fields=fields_with_org,
        submit_text="Create Opportunity",
        submit_color="green",
    )
    return await render_template(ctx.request, "pages/shared.html", user=user, **context)


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
    """Create a new opportunity."""
    user = ctx.require_authenticated()
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
            return await handle_htmx_redirect(ctx, "/opportunities")

        return await ctx.success_response(data=OpportunityResponse.model_validate(opportunity), status_code=201)
    except HTTPException as e:
        return await ctx.error_response(e, template="pages/shared.html", view="form", block="form_content")


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

        return await ctx.success_response(
            template="pages/opportunities.html",
            block="opp_detail" if ctx.is_htmx else None,
            opportunity=opportunity,
            user_application=user_application,
            is_admin=is_admin,
        )

    return await ctx.success_response(data=OpportunityResponse.model_validate(opportunity))


@router.get("/opportunities/{opportunity_id}/apply", response_model=None, responses=error_responses(auth=True))
async def apply_form(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    app_svc: ApplicationServiceDep,
    opportunity_id: UUID,
) -> Response:
    """Show application form for an opportunity."""
    user = ctx.require_authenticated()
    require_volunteer_role(user)

    opportunity = await opp_svc.get_by_id(opportunity_id)
    if await app_svc.check_already_applied(user.id, opportunity_id):
        return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)

    return await render_template(
        ctx.request,
        "pages/opportunities.html",
        view="apply",
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
    """Apply to an opportunity."""
    user = ctx.require_authenticated()
    require_volunteer_role(user)

    data = await ctx.parse_body_or_400(ApplicationCreate, {"message": "message"})
    if ctx.is_ui:
        opportunity = await opp_svc.get_by_id(opportunity_id)

    try:
        application = await app_svc.apply(
            opportunity_id=opportunity_id,
            volunteer_id=user.id,
            message=data.message,
        )

        if ctx.is_ui:
            return await handle_htmx_redirect(ctx, f"/opportunities/{opportunity_id}")

        return await ctx.success_response(data=ApplicationResponse.model_validate(application), status_code=201)
    except HTTPException as e:
        if ctx.is_ui:
            return await ctx.error_response(
                e, template="pages/opportunities.html", view="apply", block="form_content", opportunity=opportunity
            )
        raise


@router.get("/applications", response_model=None, responses=error_responses(auth=True))
async def list_user_applications(ctx: ContextDep, app_svc: ApplicationServiceDep) -> Response:
    """List all applications for the current user."""
    user = ctx.require_authenticated()

    if ctx.is_ui:
        applications = await app_svc.get_by_volunteer_with_opportunity(user.id)
        context = list_view_context(
            items=applications,
            page_title="My Applications",
            resource_type="application",
            create_url="/opportunities",
            create_text="Browse Opportunities",
            create_color="blue",
            show_create=len(applications) > 0,
            empty_message="You haven't applied to any opportunities yet",
            grid_cols="space-y-4",
        )
        return await render_template(ctx.request, "pages/shared.html", view="list", user=user, **context)

    applications = await app_svc.get_by_volunteer(user.id)
    return await ctx.success_response(
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

    return await ctx.success_response(data=ApplicationResponse.model_validate(application))


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


@router.delete(
    "/opportunities/{opportunity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(auth=True, forbidden=True, not_found=True),
)
async def delete_opportunity(
    opportunity_id: UUID,
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Soft-delete an opportunity (admins only)."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id_including_deleted(opportunity_id)
    await org_svc.require_admin(user.id, opportunity.organization_id)
    await opp_svc.soft_delete(opportunity_id)
    return Response(status_code=204)


@router.post("/opportunities/{opportunity_id}/delete", include_in_schema=False)
async def delete_opportunity_post(
    opportunity_id: UUID,
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Soft-delete an opportunity via UI POST (admins only)."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id_including_deleted(opportunity_id)
    await org_svc.require_admin(user.id, opportunity.organization_id)
    await opp_svc.soft_delete(opportunity_id)
    return await handle_htmx_redirect(ctx, "/opportunities")


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
            return await ctx.success_response(
                template="pages/opportunities.html",
                block="user_application_status",
                opportunity=opportunity,
            )
        # We are on list page, return empty string to remove card
        return Response(content="", media_type="text/html")

    return await ctx.success_response(redirect_url="/applications")


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
    context = list_view_context(
        items=applications,
        page_title=f"Applicants - {opportunity.title}",
        resource_type="applicant",
        create_url=f"/opportunities/{opportunity_id}",
        create_text="Back to Opportunity",
        create_color="blue",
        show_create=False,
        empty_message="No applications yet. Applications will appear here when volunteers apply to this opportunity.",
        grid_cols="space-y-4",
    )
    return await render_template(
        ctx.request,
        "pages/opportunities/applicants.html",
        view="list",
        user=user,
        opportunity=opportunity,
        **context,
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


@router.post(
    "/opportunities/{opportunity_id}/banner", response_model=OpportunityResponse, responses=error_responses(auth=True)
)
async def upload_opportunity_banner(
    opportunity_id: UUID,
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
    image_svc: ImageServiceDep,
    file: Annotated[UploadFile, File(...)],
) -> OpportunityResponse:
    """Upload opportunity banner image."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id(opportunity_id)

    # Check permission
    await org_svc.require_admin(user.id, opportunity.organization_id)

    # Use ImageService to process file
    content = await file.read()
    filename = await run_in_threadpool(
        image_svc.process_and_save,
        content,
        opportunity_id,
        ImagePreset.BANNER,
    )

    # Update database
    opportunity = await opp_svc.update_banner(opportunity.id, filename)

    return OpportunityResponse.model_validate(opportunity)
