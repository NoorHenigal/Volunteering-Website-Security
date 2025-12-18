"""Demo mode endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from app.core.config import settings
from app.core.context import ContextDep
from app.core.htmx import trigger_toast
from app.db.seed import is_demo_seeded, seed_demo_data, unseed_demo_data
from app.db.session import AsyncSessionLocal
from app.demo.bot import (
    clear_demo_conversation,
    get_active_bot_session,
    send_bot_reply,
    start_demo_bot_conversation,
)

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
    response.headers["HX-Trigger-After-Swap"] = "demo-data-changed"
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

    response.headers["HX-Trigger-After-Swap"] = "demo-data-changed"
    return await trigger_toast(response, "Demo data removed", "success")


@router.get("/demo/messaging")
async def demo_messaging_panel(ctx: ContextDep) -> Response:
    """Render the demo messaging panel for the inbox page."""
    await _require_demo_enabled()
    user = ctx.require_authenticated()
    seeded = await is_demo_seeded(ctx.db)
    session = get_active_bot_session(user.id)
    return await ctx.success_response(
        template="components/demo_messaging_panel.html",
        seeded=seeded,
        has_active_bot=session is not None,
    )


@router.post("/demo/bot/start")
async def demo_bot_start(ctx: ContextDep) -> Response:
    """Start a demo bot conversation with a random demo user."""
    await _require_demo_enabled()
    user = ctx.require_authenticated()

    if not await is_demo_seeded(ctx.db):
        response = await ctx.success_response(
            template="components/demo_messaging_panel.html",
            seeded=False,
            has_active_bot=False,
        )
        return await trigger_toast(response, "Seed demo data first", "warning")

    existing = get_active_bot_session(user.id)
    if existing:
        response = await ctx.success_response(
            template="components/demo_messaging_panel.html",
            seeded=True,
            has_active_bot=True,
        )
        return await trigger_toast(response, "Demo bot already active", "info")

    result = await start_demo_bot_conversation(ctx.db, user)
    if not result:
        response = await ctx.success_response(
            template="components/demo_messaging_panel.html",
            seeded=True,
            has_active_bot=False,
        )
        return await trigger_toast(response, "Failed to start demo bot", "error")

    conversation, bot_user, _ = result

    response = await ctx.success_response(
        template="components/demo_messaging_panel.html",
        seeded=True,
        has_active_bot=True,
        bot_name=bot_user.display_name,
        conversation_id=str(conversation.id),
    )
    response.headers["HX-Trigger-After-Swap"] = "demo-bot-started"
    return await trigger_toast(response, f"{bot_user.display_name} sent you a message!")


@router.post("/demo/bot/reply")
async def demo_bot_reply(ctx: ContextDep, background_tasks: BackgroundTasks) -> Response:
    """Trigger the demo bot to reply (called after user sends a message)."""
    await _require_demo_enabled()
    user = ctx.require_authenticated()

    session = get_active_bot_session(user.id)
    if not session:
        return Response(status_code=204)

    async def _send_reply() -> None:
        await asyncio.sleep(0.5)
        async with AsyncSessionLocal() as db:
            await send_bot_reply(db, user.id)
            await db.commit()

    background_tasks.add_task(_send_reply)
    return Response(status_code=204)


@router.post("/demo/bot/stop")
async def demo_bot_stop(ctx: ContextDep) -> Response:
    """Stop the demo bot and clear the conversation."""
    await _require_demo_enabled()
    user = ctx.require_authenticated()

    await clear_demo_conversation(ctx.db, user.id)

    response = await ctx.success_response(
        template="components/demo_messaging_panel.html",
        seeded=await is_demo_seeded(ctx.db),
        has_active_bot=False,
    )
    response.headers["HX-Trigger-After-Swap"] = "demo-bot-stopped"
    return await trigger_toast(response, "Demo bot stopped")
