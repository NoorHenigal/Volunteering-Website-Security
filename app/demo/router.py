"""Demo mode UI endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.core.config import settings
from app.core.context import ContextDep
from app.core.htmx import trigger_toast
from app.db.seed import is_demo_seeded, seed_demo_data, unseed_demo_data

router = APIRouter(tags=["Demo"], include_in_schema=False)


async def _require_demo_enabled() -> None:
    if not settings.demo_data:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/demo/settings")
async def demo_settings(ctx: ContextDep) -> Response:
    """Render the demo settings modal body."""
    await _require_demo_enabled()
    seeded = await is_demo_seeded(ctx.db)
    can_manage = ctx.user is not None
    return await ctx.success_response(
        template="components/demo_settings.html",
        seeded=seeded,
        can_manage=can_manage,
    )


@router.post("/demo/seed")
async def demo_seed(ctx: ContextDep) -> Response:
    """Seed demo data for the current environment."""
    await _require_demo_enabled()
    ctx.require_authenticated()

    if await is_demo_seeded(ctx.db):
        response = await ctx.success_response(
            template="components/demo_settings.html",
            seeded=True,
            can_manage=True,
        )
        return await trigger_toast(response, "Demo data already seeded", "info")

    await seed_demo_data(ctx.db)
    response = await ctx.success_response(
        template="components/demo_settings.html",
        seeded=True,
        can_manage=True,
    )
    return await trigger_toast(response, "Demo data seeded")


@router.post("/demo/unseed")
async def demo_unseed(ctx: ContextDep) -> Response:
    """Remove demo data for the current environment."""
    await _require_demo_enabled()
    ctx.require_authenticated()

    removed = await unseed_demo_data(ctx.db)
    seeded = await is_demo_seeded(ctx.db)

    response = await ctx.success_response(
        template="components/demo_settings.html",
        seeded=seeded,
        can_manage=True,
    )

    if not removed:
        return await trigger_toast(response, "No demo data to remove", "info")

    return await trigger_toast(response, "Demo data removed", "success")
