"""Report routes for content moderation."""

from uuid import UUID

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

from app.core.context import ContextDep, render_template, require_system_admin, ui_auth_required
from app.core.dependencies import ReportServiceDep
from app.core.htmx import handle_htmx_redirect, trigger_toast
from app.core.types import UI_RESPONSES
from app.db.models import User
from app.reports.schemas import REPORT_REASONS, ReportCreate, ReportResolve

router = APIRouter(
    tags=["Reports"],
    default_response_class=HTMLResponse,
    responses=UI_RESPONSES,
)


@router.post("/reports")
@ui_auth_required
async def create_report(
    ctx: ContextDep,
    user: User,
    report_svc: ReportServiceDep,
) -> Response:
    """Submit a report for content moderation."""
    data = await ctx.parse_body_or_400(
        ReportCreate,
        {
            "target_type": "target_type",
            "target_id": "target_id",
            "reason": "reason",
            "description": "description",
        },
    )

    await report_svc.create_report(
        reporter_id=user.id,
        target_type=data.target_type,
        target_id=data.target_id,
        reason=data.reason,
        description=data.description,
    )

    if ctx.is_htmx:
        response = Response(
            content='<div class="text-green-600 text-sm font-medium">Report submitted successfully</div>',
            media_type="text/html",
        )
        return await trigger_toast(
            response, "Report submitted. Thank you for helping keep our community safe.", "success"
        )

    return await handle_htmx_redirect(ctx, "/")


@router.get("/admin/reports")
async def admin_reports_page(
    ctx: ContextDep,
    report_svc: ReportServiceDep,
    page: int = 1,
) -> Response:
    """Show admin reports queue page."""
    user = ctx.require_authenticated()
    require_system_admin(user)

    reports, total = await report_svc.get_pending_reports(page=page, limit=20)
    total_pages = (total + 19) // 20

    return await render_template(
        ctx.request,
        "pages/admin/reports.html",
        user=user,
        reports=reports,
        page=page,
        total=total,
        total_pages=total_pages,
        active_tab="reports",
        report_reasons=REPORT_REASONS,
    )


@router.get("/admin/reports/{report_id}")
async def admin_report_detail(
    ctx: ContextDep,
    report_svc: ReportServiceDep,
    report_id: UUID,
) -> Response:
    """Show report detail page."""
    user = ctx.require_authenticated()
    require_system_admin(user)

    report = await report_svc.get_report_by_id(report_id)

    return await render_template(
        ctx.request,
        "pages/admin/report_detail.html",
        user=user,
        report=report,
        active_tab="reports",
        report_reasons=REPORT_REASONS,
    )


@router.post("/admin/reports/{report_id}/resolve")
async def resolve_report(
    ctx: ContextDep,
    report_svc: ReportServiceDep,
    report_id: UUID,
) -> Response:
    """Resolve a report (delete content or reject report)."""
    user = ctx.require_authenticated()
    require_system_admin(user)

    data = await ctx.parse_body_or_400(ReportResolve, {"action": "action"})

    await report_svc.resolve_report(
        report_id=report_id,
        admin_id=user.id,
        action=data.action,
    )

    action_msg = "Content deleted" if data.action == "delete" else "Report rejected"

    if ctx.is_htmx:
        response = await handle_htmx_redirect(ctx, "/admin/reports")
        return await trigger_toast(response, action_msg, "success")

    return await handle_htmx_redirect(ctx, "/admin/reports")


__all__ = ["router"]
