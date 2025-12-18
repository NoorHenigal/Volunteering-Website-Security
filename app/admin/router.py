"""Admin routes for system administration."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.service import AdminService
from app.core.context import ContextDep, render_template, require_system_admin
from app.core.types import UI_RESPONSES
from app.db.models import User

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    default_response_class=HTMLResponse,
    responses=UI_RESPONSES,
)


def get_admin_service(ctx: ContextDep) -> AdminService:
    """Get admin service dependency."""
    return AdminService(ctx.db)


AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


def _require_admin(ctx: ContextDep) -> User:
    """Require authenticated system admin user."""
    user = ctx.require_authenticated()
    require_system_admin(user)
    return user


@router.get("/dashboard", include_in_schema=False)
async def admin_dashboard(ctx: ContextDep, admin_svc: AdminServiceDep) -> Response:
    """Show admin dashboard with platform statistics."""
    user = _require_admin(ctx)

    if user.requires_password_reset:
        return RedirectResponse(url="/auth/login", status_code=303)

    stats = await admin_svc.get_platform_stats()

    return await render_template(
        ctx.request,
        "pages/admin/dashboard.html",
        user=user,
        stats=stats,
    )


__all__ = ["router"]
