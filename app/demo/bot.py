"""Demo bot for simulating real-time messaging interactions."""

import asyncio
import random
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, User
from app.db.seed import get_active_demo_seed_run
from app.messaging.service import MessagingService
from app.messaging.websocket import manager

if TYPE_CHECKING:
    from faker import Faker

_fake: Faker | None = None


def _get_faker() -> Faker:
    """Get the Faker instance, initializing if needed (prefer calling init_faker on startup)."""
    global _fake  # noqa: PLW0603
    if _fake is None:
        from faker import Faker  # noqa: PLC0415

        _fake = Faker("en_US")
    return _fake


def init_faker() -> None:
    """Initialize Faker instance. Call this on app startup to avoid slow first request."""
    _get_faker()


class DemoBotSession:
    """Tracks an active demo bot session for a user."""

    __slots__ = ("bot_user_id", "conversation_id", "user_id")

    def __init__(self, user_id: UUID, bot_user_id: UUID, conversation_id: UUID) -> None:  # noqa: D107
        self.user_id = user_id
        self.bot_user_id = bot_user_id
        self.conversation_id = conversation_id


# In-memory store for active demo bot sessions (user_id -> session)
_active_sessions: dict[UUID, DemoBotSession] = {}


def get_active_bot_session(user_id: UUID) -> DemoBotSession | None:
    """Get the active demo bot session for a user."""
    return _active_sessions.get(user_id)


def clear_bot_session(user_id: UUID) -> DemoBotSession | None:
    """Clear and return the demo bot session for a user."""
    return _active_sessions.pop(user_id, None)


def set_bot_session(user_id: UUID, session: DemoBotSession) -> None:
    """Set the demo bot session for a user."""
    _active_sessions[user_id] = session


def generate_random_message(min_words: int = 3, max_words: int = 15) -> str:
    """Generate a random message with 3-15 words using Faker."""
    word_count = random.randint(min_words, max_words)  # noqa: S311
    return _get_faker().sentence(nb_words=word_count, variable_nb_words=False)


async def get_random_demo_user(db: AsyncSession, exclude_user_id: UUID) -> User | None:
    """Get a random demo user from the active seed run, excluding the current user."""
    run = await get_active_demo_seed_run(db)
    if not run:
        return None

    result = await db.execute(
        select(User).where(
            User.demo_seed_run_id == run.id,
            User.id != exclude_user_id,
            User.role == "volunteer",
        )
    )
    demo_users = list(result.scalars().all())
    if not demo_users:
        return None

    return random.choice(demo_users)  # noqa: S311


async def start_demo_bot_conversation(
    db: AsyncSession,
    user: User,
) -> tuple[Conversation, User, Message] | None:
    """Start a demo bot conversation with a random demo user.

    Returns (conversation, bot_user, initial_message) or None if not seeded.
    """
    bot_user = await get_random_demo_user(db, user.id)
    if not bot_user:
        return None

    svc = MessagingService(db)
    conversation = await svc.get_or_create_dm("user", user.id, "user", bot_user.id)

    initial_content = generate_random_message()
    message = await svc.send_message(conversation.id, "user", bot_user.id, initial_content)

    set_bot_session(user.id, DemoBotSession(user.id, bot_user.id, conversation.id))

    await manager.notify_inbox_update(
        conversation.id,
        [("user", user.id), ("user", bot_user.id)],
        initial_content,
        bot_user.display_name,
        message.created_at.isoformat(),
    )

    return conversation, bot_user, message


async def send_bot_reply(
    db: AsyncSession,
    user_id: UUID,
) -> Message | None:
    """Send a bot reply in the active demo conversation.

    Simulates typing for 1-3 seconds before sending.
    Returns the sent message or None if no active session.
    """
    session = get_active_bot_session(user_id)
    if not session:
        return None

    bot_user = await db.get(User, session.bot_user_id)
    if not bot_user:
        return None

    typing_duration = random.uniform(1.0, 3.0)  # noqa: S311
    await manager.send_typing_indicator(
        session.conversation_id,
        "user",
        session.bot_user_id,
        bot_user.display_name,
        is_typing=True,
    )

    await asyncio.sleep(typing_duration)

    await manager.send_typing_indicator(
        session.conversation_id,
        "user",
        session.bot_user_id,
        bot_user.display_name,
        is_typing=False,
    )

    reply_content = generate_random_message()
    svc = MessagingService(db)
    message = await svc.send_message(
        session.conversation_id,
        "user",
        session.bot_user_id,
        reply_content,
    )

    await manager.send_new_message(
        session.conversation_id,
        message,
        bot_user.display_name,
        bot_user.profile_picture,
    )

    await manager.notify_inbox_update(
        session.conversation_id,
        [("user", session.user_id), ("user", session.bot_user_id)],
        reply_content,
        bot_user.display_name,
        message.created_at.isoformat(),
    )

    return message


async def clear_demo_conversation(db: AsyncSession, user_id: UUID) -> bool:
    """Clear all messages in the demo bot conversation and end the session.

    Returns True if cleared, False if no active session.
    """
    session = clear_bot_session(user_id)
    if not session:
        return False

    await db.execute(Message.__table__.delete().where(Message.conversation_id == session.conversation_id))
    await db.execute(Conversation.__table__.delete().where(Conversation.id == session.conversation_id))
    await db.flush()

    return True
