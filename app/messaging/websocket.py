"""WebSocket connection manager for real-time messaging."""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

from fastapi import WebSocket

from app.db.models import Message

logger = logging.getLogger(__name__)

MESSAGE_PREVIEW_MAX_LENGTH = 50


class MessagePayloadData(TypedDict):
    """Payload data for a new message."""

    id: str
    content: str
    sender_type: str
    sender_id: str
    sender_name: str
    sender_avatar: str | None
    created_at: str


class NewMessagePayload(TypedDict):
    """WebSocket payload for new message broadcast."""

    type: str
    message: MessagePayloadData


class TypingPayload(TypedDict):
    """WebSocket payload for typing indicator."""

    type: str
    sender_type: str
    sender_id: str
    sender_name: str
    is_typing: bool


class ReadReceiptPayload(TypedDict):
    """WebSocket payload for read receipt."""

    type: str
    reader_type: str
    reader_id: str
    read_at: str


WebSocketPayload = NewMessagePayload | TypingPayload | ReadReceiptPayload


class ConnectionManager:
    """Manages WebSocket connections for real-time messaging.

    Tracks active connections per conversation and provides methods
    for broadcasting messages and typing indicators.
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        # Map: conversation_id --> list of (entity_type, entity_id, websocket)
        self.active_connections: dict[UUID, list[tuple[str, UUID, WebSocket]]] = defaultdict(list)
        # Map: (entity_type, entity_id) --> list of websockets for inbox updates
        self.inbox_connections: dict[tuple[str, UUID], list[WebSocket]] = defaultdict(list)
        # Map: (conversation_id, entity_type, entity_id) --> last_typing_time
        self.typing_states: dict[tuple[UUID, str, UUID], datetime] = {}

    async def connect(
        self,
        websocket: WebSocket,
        conversation_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> None:
        """Accept a WebSocket connection and register it."""
        await websocket.accept()
        self.active_connections[conversation_id].append((entity_type, entity_id, websocket))

    def disconnect(self, websocket: WebSocket, conversation_id: UUID) -> None:
        """Remove a WebSocket connection from the registry."""
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id] = [
                conn for conn in self.active_connections[conversation_id] if conn[2] != websocket
            ]
            # Clean up empty conversation entries
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]

    def get_connection_count(self, conversation_id: UUID) -> int:
        """Get the number of active connections for a conversation."""
        return len(self.active_connections.get(conversation_id, []))

    async def broadcast_to_conversation(
        self,
        conversation_id: UUID,
        message: WebSocketPayload,
        exclude: tuple[str, UUID] | None = None,
    ) -> None:
        """Broadcast a message to all participants in a conversation.

        Args:
            conversation_id: The conversation to broadcast to.
            message: The message payload to send.
            exclude: Optional (entity_type, entity_id) tuple to exclude from broadcast.
        """
        if conversation_id not in self.active_connections:
            return

        disconnected = []
        for entity_type, entity_id, ws in self.active_connections[conversation_id]:
            if exclude and (entity_type, entity_id) == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                disconnected.append(ws)

        # Clean up disconnected sockets
        for ws in disconnected:
            self.disconnect(ws, conversation_id)

    async def send_new_message(
        self,
        conversation_id: UUID,
        message: Message,
        sender_name: str,
        sender_avatar: str | None = None,
    ) -> None:
        """Broadcast a new message to all conversation participants."""
        message_data: MessagePayloadData = {
            "id": str(message.id),
            "content": message.content,
            "sender_type": message.sender_type,
            "sender_id": str(message.sender_id),
            "sender_name": sender_name,
            "sender_avatar": sender_avatar,
            "created_at": message.created_at.isoformat(),
        }
        payload: NewMessagePayload = {
            "type": "new_message",
            "message": message_data,
        }
        await self.broadcast_to_conversation(conversation_id, payload)

    async def send_typing_indicator(
        self,
        conversation_id: UUID,
        entity_type: str,
        entity_id: UUID,
        sender_name: str,
        is_typing: bool,
    ) -> None:
        """Broadcast typing indicator to other participants."""
        key = (conversation_id, entity_type, entity_id)

        if is_typing:
            self.typing_states[key] = datetime.now(UTC)
        elif key in self.typing_states:
            del self.typing_states[key]

        payload: TypingPayload = {
            "type": "typing",
            "sender_type": entity_type,
            "sender_id": str(entity_id),
            "sender_name": sender_name,
            "is_typing": is_typing,
        }
        await self.broadcast_to_conversation(
            conversation_id,
            payload,
            exclude=(entity_type, entity_id),
        )

    async def send_read_receipt(
        self,
        conversation_id: UUID,
        entity_type: str,
        entity_id: UUID,
        read_at: datetime,
    ) -> None:
        """Broadcast read receipt to other participants."""
        payload: ReadReceiptPayload = {
            "type": "read_receipt",
            "reader_type": entity_type,
            "reader_id": str(entity_id),
            "read_at": read_at.isoformat(),
        }
        await self.broadcast_to_conversation(
            conversation_id,
            payload,
            exclude=(entity_type, entity_id),
        )

    async def connect_inbox(
        self,
        websocket: WebSocket,
        entity_type: str,
        entity_id: UUID,
    ) -> None:
        """Register a WebSocket for inbox updates."""
        await websocket.accept()
        key = (entity_type, entity_id)
        self.inbox_connections[key].append(websocket)

    def disconnect_inbox(
        self,
        websocket: WebSocket,
        entity_type: str,
        entity_id: UUID,
    ) -> None:
        """Remove a WebSocket from inbox updates."""
        key = (entity_type, entity_id)
        if key in self.inbox_connections:
            self.inbox_connections[key] = [ws for ws in self.inbox_connections[key] if ws != websocket]
            if not self.inbox_connections[key]:
                del self.inbox_connections[key]

    async def notify_inbox_update(
        self,
        conversation_id: UUID,
        participant_entities: list[tuple[str, UUID]],
        message_preview: str,
        sender_name: str,
        last_message_at: str,
    ) -> None:
        """Notify all participants' inboxes about a new message."""
        preview = (
            message_preview[:MESSAGE_PREVIEW_MAX_LENGTH] + "..."
            if len(message_preview) > MESSAGE_PREVIEW_MAX_LENGTH
            else message_preview
        )
        payload = {
            "type": "inbox_update",
            "conversation_id": str(conversation_id),
            "message_preview": preview,
            "sender_name": sender_name,
            "last_message_at": last_message_at,
        }

        for entity_type, entity_id in participant_entities:
            key = (entity_type, entity_id)
            if key not in self.inbox_connections:
                continue

            disconnected = []
            for ws in self.inbox_connections[key]:
                try:
                    await ws.send_json(payload)
                except Exception:  # noqa: BLE001
                    disconnected.append(ws)

            for ws in disconnected:
                self.disconnect_inbox(ws, entity_type, entity_id)


# Global connection manager instance
manager = ConnectionManager()


__all__ = ["ConnectionManager", "manager"]
