"""Messaging schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.base_schemas import BaseOut, StrictModel
from app.db.models import ParticipantType


class MessageCreate(StrictModel):
    """Create a new message."""

    content: str = Field(min_length=1, max_length=5000)


class StartConversationRequest(StrictModel):
    """Request to start a conversation."""

    recipient_type: ParticipantType
    recipient_id: UUID


class ParticipantInfo(StrictModel):
    """Information about a conversation participant."""

    type: ParticipantType
    id: UUID
    name: str
    username: str
    profile_picture: str | None = None
    logo: str | None = None


class MessageResponse(BaseOut):
    """Message response."""

    conversation_id: UUID
    sender_type: ParticipantType
    sender_id: UUID
    content: str


class ConversationResponse(BaseOut):
    """Conversation response for inbox."""

    dm_key: str
    last_message_at: datetime | None
    has_unread: bool = False
    other_party: ParticipantInfo | None = None
    last_message_preview: str | None = None


class ConversationDetailResponse(ConversationResponse):
    """Conversation detail with messages."""

    messages: list[MessageResponse] = Field(default_factory=list)
