"""Opportunity and application routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.core.context import (
    ContextDep,
    render_template,
    require_volunteer_role,
)
from app.core.context_types import list_view_context
from app.core.dependencies import (
    ApplicationServiceDep,
    ImageServiceDep,
    OpportunityServiceDep,
    OrganizationServiceDep,
)
from app.core.htmx import handle_htmx_redirect, render_block
from app.core.services.images import ImagePreset
from app.core.types import UI_RESPONSES
from app.opportunities.schemas import (
    ApplicationCreate,
    ApplicationStatusUpdate,
    OpportunityCreate,
)

router = APIRouter(
    tags=["Opportunities"],
    default_response_class=HTMLResponse,
    responses=UI_RESPONSES,
)


@router.get("/opportunities")
async def list_opportunities(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    page: int = 1,
) -> Response:
    """List all open opportunities."""
    user = ctx.require_authenticated()
    limit = 9

    items, total = await opp_svc.list_open(page=page, limit=limit)

    user_orgs = await opp_svc.get_user_organizations(user.id)
    org_options = [(str(org.id), org.name) for org in user_orgs]

    context = list_view_context(
        items=items,
        page_title="Volunteering Opportunities",
        meta={"page": page, "total": total, "per_page": limit, "total_pages": (total + limit - 1) // limit},
        show_create=user is not None,
        empty_message="No opportunities available at the moment.",
    )

    return await ctx.success_response(
        template="pages/opportunities/list.html",
        organizations=org_options,
        **context,
    )


@router.post("/opportunities")
async def create_opportunity(
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
) -> Response:
    """Create a new opportunity."""
    user = ctx.require_authenticated()

    try:
        data = await ctx.parse_body_or_400(
            OpportunityCreate,
            {
                "title": "title",
                "description": "description",
                "organization_id": "organization_id",
                "location": "location",
            },
        )
    except HTTPException as e:
        if ctx.is_htmx:
            return await ctx.error_response(e, template=None, block=None)
        return await ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", page_title="Opportunities"
        )

    try:
        await org_svc.get_by_id(data.organization_id)
        await org_svc.require_member(user.id, data.organization_id)
    except HTTPException as e:
        if ctx.is_htmx:
            return await ctx.error_response(e, template=None, block=None)
        return await ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", page_title="Opportunities"
        )

    try:
        opportunity = await opp_svc.create(
            title=data.title,
            description=data.description,
            organization_id=data.organization_id,
            posted_by=user.id,
            location=data.location,
        )

        return await handle_htmx_redirect(ctx, f"/opportunities/{opportunity.id}")
    except HTTPException as e:
        if ctx.is_htmx:
            return await ctx.error_response(e, template=None, block=None)
        return await ctx.error_response(
            e, template="pages/shared.html", view="form", block="form_content", page_title="Opportunities"
        )


@router.get("/opportunities/{opportunity_id}")
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

    user_application = None
    if user.role == "volunteer":
        user_application = await app_svc.check_already_applied(user.id, opportunity_id)

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


@router.get("/opportunities/{opportunity_id}/apply")
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


@router.post("/opportunities/{opportunity_id}/apply")
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
    opportunity = await opp_svc.get_by_id(opportunity_id)

    try:
        await app_svc.apply(
            opportunity_id=opportunity_id,
            volunteer_id=user.id,
            message=data.message,
        )

        if ctx.is_htmx:
            user_application = await app_svc.check_already_applied(user.id, opportunity_id)
            return await render_block(
                ctx.request,
                "pages/opportunities.html",
                "user_application_status",
                opportunity=opportunity,
                user_application=user_application,
                user=ctx.user,
            )
        return await handle_htmx_redirect(ctx, f"/opportunities/{opportunity_id}")
    except HTTPException as e:
        if ctx.is_htmx:
            return await ctx.error_response(e, template=None, block=None)
        return await ctx.error_response(
            e, template="pages/opportunities.html", view="apply", block="form_content", opportunity=opportunity
        )


@router.get("/applications")
async def list_user_applications(ctx: ContextDep, app_svc: ApplicationServiceDep) -> Response:
    """List all applications for the current user."""
    user = ctx.require_authenticated()

    applications = await app_svc.get_by_volunteer_with_opportunity(user.id)
    context = list_view_context(
        items=applications,
        page_title="My Applications",
        resource_type="application",
        create_url="/opportunities",
        create_text="Browse Opportunities",
        create_color="blue",
        show_create=True,
        empty_message="You haven't applied to any opportunities yet",
        grid_cols="space-y-4",
    )
    return await render_template(ctx.request, "pages/shared.html", view="list", user=user, **context)


@router.put("/applications/{application_id}/status")
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

    await org_svc.require_admin(user.id, opportunity.organization_id)

    await app_svc.update_status(application, data.status)

    # Redirect back to applicants list
    return RedirectResponse(url=f"/opportunities/{opportunity.id}/applicants", status_code=303)


@router.delete("/applications/{application_id}")
async def withdraw_application(
    application_id: UUID,
    ctx: ContextDep,
    app_svc: ApplicationServiceDep,
    opp_svc: OpportunityServiceDep,
) -> Response:
    """Withdraw an application (volunteers only)."""
    user = ctx.require_authenticated()
    require_volunteer_role(user)
    application = await app_svc.get_by_id(application_id)
    opportunity = await opp_svc.get_by_id(application.opportunity_id)
    await app_svc.withdraw(application_id, user)

    if ctx.is_htmx:
        return await render_block(
            ctx.request,
            "pages/opportunities.html",
            "user_application_status",
            opportunity=opportunity,
            user_application=None,
            user=ctx.user,
        )

    return await ctx.success_response(redirect_url="/applications")


@router.delete("/opportunities/{opportunity_id}")
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
    return await handle_htmx_redirect(ctx, "/opportunities")


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
    application = await app_svc.get_by_id(application_id)
    opportunity = await opp_svc.get_by_id(application.opportunity_id)

    await app_svc.withdraw(application_id, user)

    if ctx.is_htmx:
        return await render_block(
            ctx.request,
            "pages/opportunities.html",
            "user_application_status",
            opportunity=opportunity,
            user_application=None,
            user=ctx.user,
        )

    return await ctx.success_response(redirect_url="/applications")


@router.get("/opportunities/{opportunity_id}/applicants")
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


@router.post("/opportunities/{opportunity_id}/banner")
async def upload_opportunity_banner(
    opportunity_id: UUID,
    ctx: ContextDep,
    opp_svc: OpportunityServiceDep,
    org_svc: OrganizationServiceDep,
    image_svc: ImageServiceDep,
    file: Annotated[UploadFile, File(...)],
) -> Response:
    """Upload opportunity banner image."""
    user = ctx.require_authenticated()
    opportunity = await opp_svc.get_by_id(opportunity_id)

    await org_svc.require_admin(user.id, opportunity.organization_id)

    content = await file.read()
    filename = await run_in_threadpool(
        image_svc.process_and_save,
        content,
        opportunity_id,
        ImagePreset.BANNER,
    )
    await opp_svc.update_banner(opportunity.id, filename)

    return await handle_htmx_redirect(ctx, f"/opportunities/{opportunity_id}")
