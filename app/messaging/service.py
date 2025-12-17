"""Messaging service with business logic and authorization."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import forbid
from app.core.service import BaseService
from app.core.services.encryption import encrypt_field
from app.db.models import Conversation, ConversationParticipant, Message, ParticipantType
from app.db.repositories import (
    ConversationParticipantRepository,
    ConversationRepository,
    MessageRepository,
    OrganizationRepository,
    UserOrganizationRoleRepository,
    UserRepository,
)
from app.messaging.schemas import ConversationResponse, ParticipantInfo


class MessagingService(BaseService):
    """Business logic for messaging with authorization."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize messaging service with repositories."""
        super().__init__(db)
        self._conv_repo = ConversationRepository(db)
        self._participant_repo = ConversationParticipantRepository(db)
        self._msg_repo = MessageRepository(db)
        self._org_role_repo = UserOrganizationRoleRepository(db)
        self._user_repo = UserRepository(db)
        self._org_repo = OrganizationRepository(db)

    async def can_act_as_org(self, user_id: UUID, org_id: UUID) -> bool:
        """Check if user can send/read messages as this organization.

        Uses membership check (not admin-only) per authorization design.
        """
        return await self._org_role_repo.is_organization_member(user_id, org_id)

    async def require_can_act_as_org(self, user_id: UUID, org_id: UUID) -> None:
        """Raise 403 if user cannot act as org."""
        forbid(
            not await self.can_act_as_org(user_id, org_id),
            "You must be a member of this organization to access its messages",
        )

    async def require_participant(
        self,
        conversation_id: UUID,
        entity_type: ParticipantType,
        entity_id: UUID,
    ) -> ConversationParticipant:
        """Raise 403 if entity is not a participant."""
        participant = await self._participant_repo.get_participant(conversation_id, entity_type, entity_id)
        forbid(participant is None, "You don't have access to this conversation")
        return participant  # type: ignore[return-value]

    async def get_or_create_dm(
        self,
        sender_type: ParticipantType,
        sender_id: UUID,
        recipient_type: ParticipantType,
        recipient_id: UUID,
    ) -> Conversation:
        """Find or create DM conversation (idempotent via dm_key UNIQUE constraint).

        Handles race conditions by catching unique violation and fetching existing.
        """
        if sender_type == recipient_type and sender_id == recipient_id:
            raise HTTPException(status_code=400, detail="Cannot message yourself")

        dm_key = ConversationRepository.build_dm_key(sender_type, sender_id, recipient_type, recipient_id)

        existing = await self._conv_repo.find_by_dm_key(dm_key)
        if existing:
            return existing

        try:
            conv = Conversation(dm_key=dm_key)
            conv = await self._conv_repo.create(conv)

            p1 = ConversationParticipant(
                conversation_id=conv.id,
                user_id=sender_id if sender_type == "user" else None,
                organization_id=sender_id if sender_type == "organization" else None,
            )
            p2 = ConversationParticipant(
                conversation_id=conv.id,
                user_id=recipient_id if recipient_type == "user" else None,
                organization_id=recipient_id if recipient_type == "organization" else None,
            )
            await self._participant_repo.create(p1)
            await self._participant_repo.create(p2)
        except IntegrityError:
            await self.db.rollback()
            existing = await self._conv_repo.find_by_dm_key(dm_key)
            if existing:
                return existing
            raise HTTPException(status_code=500, detail="Failed to create conversation") from None
        else:
            return conv

    async def send_message(
        self,
        conversation_id: UUID,
        sender_type: ParticipantType,
        sender_id: UUID,
        content: str,
    ) -> Message:
        """Send a message to a conversation."""
        await self.require_participant(conversation_id, sender_type, sender_id)

        msg = Message(
            conversation_id=conversation_id,
            sender_user_id=sender_id if sender_type == "user" else None,
            sender_organization_id=sender_id if sender_type == "organization" else None,
            content_ciphertext=encrypt_field(content) or "",
        )
        msg = await self._msg_repo.create(msg)

        await self._conv_repo.update_last_message(conversation_id, msg.created_at)

        return msg

    async def get_inbox(
        self,
        entity_type: ParticipantType,
        entity_id: UUID,
        limit: int = 50,
    ) -> list[ConversationResponse]:
        """Get inbox with other party info for each conversation."""
        conversations = await self._conv_repo.get_inbox(entity_type, entity_id, limit)

        results = []
        for conv in conversations:
            conv_with_details = await self._conv_repo.get_with_participants(conv.id)
            if not conv_with_details:
                continue

            other_party = await self._get_other_party(conv_with_details, entity_type, entity_id)

            my_participant = await self._participant_repo.get_participant(conv.id, entity_type, entity_id)
            has_unread = my_participant.has_unread if my_participant else False

            latest_msg = await self._msg_repo.get_latest(conv.id)
            preview = latest_msg.content[:100] if latest_msg else None

            results.append(
                ConversationResponse(
                    id=conv.id,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    dm_key=conv.dm_key,
                    last_message_at=conv.last_message_at,
                    has_unread=has_unread,
                    other_party=other_party,
                    last_message_preview=preview,
                )
            )

        return results

    async def get_unread_count(
        self,
        entity_type: ParticipantType,
        entity_id: UUID,
    ) -> int:
        """Get count of conversations with unread messages for an entity."""
        conversations = await self.get_inbox(entity_type, entity_id)
        return sum(1 for conv in conversations if conv.has_unread)

    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        viewer_type: ParticipantType,
        viewer_id: UUID,
        limit: int = 50,
    ) -> list[Message]:
        """Get messages and mark conversation as read."""
        participant = await self.require_participant(conversation_id, viewer_type, viewer_id)

        messages = await self._msg_repo.get_messages(conversation_id, limit)

        await self._participant_repo.mark_read(participant)

        return list(reversed(messages))

    async def get_conversation_detail(
        self,
        conversation_id: UUID,
        viewer_type: ParticipantType,
        viewer_id: UUID,
    ) -> Conversation | None:
        """Get conversation with participants loaded."""
        await self.require_participant(conversation_id, viewer_type, viewer_id)
        return await self._conv_repo.get_with_participants(conversation_id)

    async def _get_other_party(
        self,
        conversation: Conversation,
        my_type: ParticipantType,
        my_id: UUID,
    ) -> ParticipantInfo | None:
        """Get info about the other participant in a conversation."""
        for p in conversation.participants:
            if p.participant_type == my_type and p.entity_id == my_id:
                continue

            if p.participant_type == "user" and p.user:
                return ParticipantInfo(
                    type="user",
                    id=p.user.id,
                    name=p.user.display_name,
                    username=p.user.username,
                    profile_picture=p.user.profile_picture,
                    logo=None,
                )
            if p.participant_type == "organization" and p.organization:
                return ParticipantInfo(
                    type="organization",
                    id=p.organization.id,
                    name=p.organization.name,
                    username=p.organization.username,
                    profile_picture=None,
                    logo=p.organization.logo,
                )

        return None

    async def get_recipient_info(
        self,
        recipient_type: ParticipantType,
        recipient_id: UUID,
    ) -> ParticipantInfo | None:
        """Get info about a potential message recipient."""
        if recipient_type == "user":
            user = await self._user_repo.get_by_id(recipient_id)
            if user:
                return ParticipantInfo(
                    type="user",
                    id=user.id,
                    name=user.display_name,
                    username=user.username,
                    profile_picture=user.profile_picture,
                    logo=None,
                )
        else:
            org = await self._org_repo.get_by_id(recipient_id)
            if org:
                return ParticipantInfo(
                    type="organization",
                    id=org.id,
                    name=org.name,
                    username=org.username,
                    profile_picture=None,
                    logo=org.logo,
                )
        return None
