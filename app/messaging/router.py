"""Messaging UI routes (HTMX/Jinja) and WebSocket endpoints."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.context import ContextDep, render_template
from app.core.htmx import handle_htmx_redirect
from app.core.security import decode_access_token
from app.db.models import Organization, ParticipantType, User
from app.db.repositories import OrganizationRepository, UserOrganizationRoleRepository, UserRepository
from app.db.session import AsyncSessionLocal
from app.messaging.schemas import MessageCreate, StartConversationRequest
from app.messaging.service import MessagingService
from app.messaging.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Messaging"])


@dataclass
class MessagingContext:
    """Resolved context for messaging operations."""

    user: User
    acting_as: ParticipantType
    acting_id: UUID
    organization: Organization | None
    svc: MessagingService
    ws_token: str


async def _resolve_context(
    ctx: ContextDep,
    org_id: UUID | None = None,
) -> MessagingContext:
    """Resolve messaging context for user or organization."""
    user = ctx.require_authenticated()
    svc = MessagingService(ctx.db)
    ws_token = ctx.request.cookies.get("access_token", "")

    if org_id:
        await svc.require_can_act_as_org(user.id, org_id)
        org_repo = OrganizationRepository(ctx.db)
        organization = await org_repo.get_by_id(org_id)
        return MessagingContext(
            user=user,
            acting_as="organization",
            acting_id=org_id,
            organization=organization,
            svc=svc,
            ws_token=ws_token,
        )

    return MessagingContext(
        user=user,
        acting_as="user",
        acting_id=user.id,
        organization=None,
        svc=svc,
        ws_token=ws_token,
    )


async def _get_user_orgs_and_counts(
    db: AsyncSession,
    user: User,
    svc: MessagingService,
    current_org_id: UUID | None = None,
) -> tuple[list[Organization], dict[str, int], int]:
    """Get user organizations and unread counts for inbox switcher."""
    org_role_repo = UserOrganizationRoleRepository(db)
    user_org_roles = await org_role_repo.get_user_organizations_with_org(user.id)
    user_organizations = [role.organization for role in user_org_roles if role.organization]

    org_unread_counts: dict[str, int] = {}
    for org in user_organizations:
        if org.id != current_org_id:
            count = await svc.get_unread_count("organization", org.id)
            org_unread_counts[str(org.id)] = count

    personal_unread_count = 0
    if user.role != "organization" and current_org_id:
        personal_unread_count = await svc.get_unread_count("user", user.id)

    return user_organizations, org_unread_counts, personal_unread_count


@router.get("/messages", include_in_schema=False)
async def inbox(ctx: ContextDep) -> Response:
    """User's personal message inbox."""
    mctx = await _resolve_context(ctx)
    user_organizations, org_unread_counts, _ = await _get_user_orgs_and_counts(ctx.db, mctx.user, mctx.svc)

    if mctx.user.role == "organization" and user_organizations:
        return RedirectResponse(url=f"/org/{user_organizations[0].id}/messages", status_code=302)

    conversations = await mctx.svc.get_inbox(mctx.acting_as, mctx.acting_id)

    return await render_template(
        ctx.request,
        "pages/messages/inbox.html",
        user=mctx.user,
        conversations=conversations,
        acting_as=mctx.acting_as,
        acting_id=mctx.acting_id,
        organization=None,
        ws_token=mctx.ws_token,
        user_organizations=user_organizations,
        org_unread_counts=org_unread_counts,
        personal_unread_count=0,
    )


async def _render_conversation(
    ctx: ContextDep,
    mctx: MessagingContext,
    conversation_id: UUID,
    partial: bool,
) -> Response:
    """Shared logic for rendering a conversation view."""
    messages = await mctx.svc.get_conversation_messages(conversation_id, mctx.acting_as, mctx.acting_id)
    conversation = await mctx.svc.get_conversation_detail(conversation_id, mctx.acting_as, mctx.acting_id)

    redirect_url = f"/org/{mctx.acting_id}/messages" if mctx.organization else "/messages"
    if not conversation:
        return await handle_htmx_redirect(ctx, redirect_url)

    other_party = await mctx.svc._get_other_party(conversation, mctx.acting_as, mctx.acting_id)

    if partial or ctx.is_htmx:
        return await render_template(
            ctx.request,
            "pages/messages/conversation_content.html",
            user=mctx.user,
            conversation=conversation,
            messages=messages,
            other_party=other_party,
            acting_as=mctx.acting_as,
            acting_id=mctx.acting_id,
            ws_token=mctx.ws_token,
            organization=mctx.organization,
        )

    conversations = await mctx.svc.get_inbox(mctx.acting_as, mctx.acting_id)
    return await render_template(
        ctx.request,
        "pages/messages/inbox.html",
        user=mctx.user,
        conversation=conversation,
        messages=messages,
        other_party=other_party,
        acting_as=mctx.acting_as,
        acting_id=mctx.acting_id,
        ws_token=mctx.ws_token,
        organization=mctx.organization,
        conversations=conversations,
        selected_conversation=conversation,
    )


@router.get("/messages/{conversation_id}", include_in_schema=False)
async def conversation_view(
    ctx: ContextDep,
    conversation_id: UUID,
    *,
    partial: Annotated[bool, Query()] = False,
) -> Response:
    """View a conversation (personal inbox context)."""
    mctx = await _resolve_context(ctx)
    return await _render_conversation(ctx, mctx, conversation_id, partial)


async def _send_message_handler(
    ctx: ContextDep,
    mctx: MessagingContext,
    conversation_id: UUID,
) -> Response:
    """Shared logic for sending a message."""
    data = await ctx.parse_body_or_400(MessageCreate, {"content": "content"})
    message = await mctx.svc.send_message(conversation_id, mctx.acting_as, mctx.acting_id, data.content)

    if ctx.is_htmx:
        return await render_template(
            ctx.request,
            "pages/messages/message_bubble.html",
            message=message,
            is_own=True,
            user=mctx.user,
            acting_as=mctx.acting_as,
            acting_id=mctx.acting_id,
        )

    redirect_url = (
        f"/org/{mctx.acting_id}/messages/{conversation_id}" if mctx.organization else f"/messages/{conversation_id}"
    )
    return await handle_htmx_redirect(ctx, redirect_url)


@router.post("/messages/{conversation_id}/send", include_in_schema=False)
async def send_message(ctx: ContextDep, conversation_id: UUID) -> Response:
    """Send a message (personal context)."""
    mctx = await _resolve_context(ctx)
    return await _send_message_handler(ctx, mctx, conversation_id)


@router.get("/messages/{conversation_id}/older", include_in_schema=False)
async def load_older_messages(ctx: ContextDep, conversation_id: UUID) -> Response:
    """Load older messages for infinite scroll."""
    mctx = await _resolve_context(ctx)
    messages = await mctx.svc.get_conversation_messages(conversation_id, mctx.acting_as, mctx.acting_id, limit=30)
    return await render_template(
        ctx.request,
        "pages/messages/conversation.html",
        block="message_list_items",
        messages=messages,
        user=mctx.user,
        acting_as=mctx.acting_as,
        acting_id=mctx.acting_id,
    )


async def _start_conversation_handler(ctx: ContextDep, mctx: MessagingContext) -> Response:
    """Shared logic for starting a conversation."""
    data = await ctx.parse_body_or_400(
        StartConversationRequest,
        {"recipient_type": "recipient_type", "recipient_id": "recipient_id"},
    )
    conversation = await mctx.svc.get_or_create_dm(
        mctx.acting_as, mctx.acting_id, data.recipient_type, data.recipient_id
    )
    redirect_url = (
        f"/org/{mctx.acting_id}/messages/{conversation.id}" if mctx.organization else f"/messages/{conversation.id}"
    )
    return await handle_htmx_redirect(ctx, redirect_url)


@router.post("/messages/start", include_in_schema=False)
async def start_conversation(ctx: ContextDep) -> Response:
    """Start or continue a DM (redirects to existing if found)."""
    mctx = await _resolve_context(ctx)
    return await _start_conversation_handler(ctx, mctx)


@router.get("/org/{org_id}/messages", include_in_schema=False)
async def org_inbox(ctx: ContextDep, org_id: UUID) -> Response:
    """Organization's message inbox."""
    mctx = await _resolve_context(ctx, org_id)
    user_organizations, org_unread_counts, personal_unread_count = await _get_user_orgs_and_counts(
        ctx.db, mctx.user, mctx.svc, org_id
    )
    conversations = await mctx.svc.get_inbox(mctx.acting_as, mctx.acting_id)

    return await render_template(
        ctx.request,
        "pages/messages/inbox.html",
        user=mctx.user,
        organization=mctx.organization,
        conversations=conversations,
        acting_as=mctx.acting_as,
        acting_id=mctx.acting_id,
        ws_token=mctx.ws_token,
        user_organizations=user_organizations,
        org_unread_counts=org_unread_counts,
        personal_unread_count=personal_unread_count,
    )


@router.get("/org/{org_id}/messages/{conversation_id}", include_in_schema=False)
async def org_conversation_view(
    ctx: ContextDep,
    org_id: UUID,
    conversation_id: UUID,
    *,
    partial: Annotated[bool, Query()] = False,
) -> Response:
    """View a conversation as organization."""
    mctx = await _resolve_context(ctx, org_id)
    return await _render_conversation(ctx, mctx, conversation_id, partial)


@router.post("/org/{org_id}/messages/{conversation_id}/send", include_in_schema=False)
async def org_send_message(ctx: ContextDep, org_id: UUID, conversation_id: UUID) -> Response:
    """Send a message as organization."""
    mctx = await _resolve_context(ctx, org_id)
    return await _send_message_handler(ctx, mctx, conversation_id)


@router.post("/org/{org_id}/messages/start", include_in_schema=False)
async def org_start_conversation(ctx: ContextDep, org_id: UUID) -> Response:
    """Start or continue a DM as organization."""
    mctx = await _resolve_context(ctx, org_id)
    return await _start_conversation_handler(ctx, mctx)


@router.websocket("/ws/messages/{conversation_id}")
async def websocket_messages(
    websocket: WebSocket,
    conversation_id: UUID,
    token: str = Query(...),
    acting_as: str = Query(default="user"),
    acting_id: str = Query(default=""),
) -> None:
    """WebSocket endpoint for real-time messaging.

    Query params:
        token: JWT access token for authentication
        acting_as: 'user' or 'organization'
        acting_id: UUID of the entity (user_id or org_id)
    """
    try:
        payload = decode_access_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid token")
        return

    entity_type: ParticipantType = "user"
    entity_id: UUID
    entity_name: str
    entity_avatar: str | None = None

    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(payload.user_id)
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return

        entity_id = user.id
        entity_name = user.display_name
        entity_avatar = user.profile_picture

        if acting_as == "organization" and acting_id:
            try:
                org_id = UUID(acting_id)
                svc = MessagingService(db)
                if await svc.can_act_as_org(user.id, org_id):
                    entity_type = "organization"
                    entity_id = org_id
                    org_repo = OrganizationRepository(db)
                    org = await org_repo.get_by_id(org_id)
                    if org:
                        entity_name = org.name
                        entity_avatar = org.logo
            except ValueError:
                pass

        # Verify participant access
        svc = MessagingService(db)
        try:
            await svc.require_participant(conversation_id, entity_type, entity_id)
        except Exception:  # noqa: BLE001
            await websocket.close(code=4003, reason="Not a participant")
            return
    # Session closed here don't hold it during WebSocket lifetime

    # Accept connection and register with manager
    await websocket.accept()
    manager.active_connections[conversation_id].append((entity_type, entity_id, websocket))

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "typing":
                is_typing = data.get("is_typing", False)
                await manager.send_typing_indicator(
                    conversation_id,
                    entity_type,
                    entity_id,
                    entity_name,
                    is_typing,
                )

            elif msg_type == "message":
                content = data.get("content", "").strip()
                if content:
                    # Send message via service (create fresh session for write)
                    async with AsyncSessionLocal() as msg_db:
                        msg_svc = MessagingService(msg_db)
                        message = await msg_svc.send_message(
                            conversation_id,
                            entity_type,
                            entity_id,
                            content,
                        )
                        # Get conversation participants for inbox notification
                        conv = await msg_svc.get_conversation_detail(conversation_id, entity_type, entity_id)
                        participants: list[tuple[str, UUID]] = []
                        if conv:
                            participants.extend((p.participant_type, p.entity_id) for p in conv.participants)
                        await msg_db.commit()
                    # Broadcast to all participants in conversation
                    await manager.send_new_message(
                        conversation_id,
                        message,
                        entity_name,
                        entity_avatar,
                    )
                    # Notify inbox connections
                    if participants:
                        await manager.notify_inbox_update(
                            conversation_id,
                            participants,
                            content,
                            entity_name,
                            message.created_at.isoformat(),
                        )

            elif msg_type == "read":
                # Mark as read and notify others
                await manager.send_read_receipt(
                    conversation_id,
                    entity_type,
                    entity_id,
                    datetime.now(UTC),
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)


@router.websocket("/ws/inbox")
async def websocket_inbox(
    websocket: WebSocket,
    token: str = Query(...),
    acting_as: str = Query(default="user"),
    acting_id: str = Query(default=""),
) -> None:
    """WebSocket endpoint for real-time inbox updates.

    Query params:
        token: JWT access token for authentication
        acting_as: 'user' or 'organization'
        acting_id: UUID of the entity (user_id or org_id)
    """
    try:
        payload = decode_access_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid token")
        return

    entity_type: ParticipantType = "user"
    entity_id: UUID

    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(payload.user_id)
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return

        entity_id = user.id

        if acting_as == "organization" and acting_id:
            try:
                org_id = UUID(acting_id)
                svc = MessagingService(db)
                if await svc.can_act_as_org(user.id, org_id):
                    entity_type = "organization"
                    entity_id = org_id
            except ValueError:
                pass
    # Session closed here

    await manager.connect_inbox(websocket, entity_type, entity_id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_inbox(websocket, entity_type, entity_id)
