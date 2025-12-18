"""Admin account setup and initialization."""

import logging
import secrets
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import hash_password
from app.core.services.encryption import encrypt_field, hash_email
from app.db.models import User

log = logging.getLogger(__name__)

TEMP_ADMIN_EMAIL = "temp-admin@volunteerapp.example"
TEMP_ADMIN_USERNAME = "system_admin"


def _generate_temp_password() -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(16))


async def check_admin_exists(db: AsyncSession) -> bool:
    """Check if any system_admin user exists."""
    result = await db.execute(select(User).where(User.role == "system_admin").limit(1))
    return result.scalar_one_or_none() is not None


async def create_initial_admin(db: AsyncSession) -> tuple[str, str] | None:
    """Create initial admin account if none exists.

    Returns:
        Tuple of (email, password) if admin was created, None if admin already exists.
    """
    if await check_admin_exists(db):
        return None

    temp_password = _generate_temp_password()

    admin_user = User(
        email_ciphertext=encrypt_field(TEMP_ADMIN_EMAIL),
        email_hash=hash_email(TEMP_ADMIN_EMAIL),
        password_hash=hash_password(temp_password),
        username=TEMP_ADMIN_USERNAME,
        role="system_admin",
        first_name="System",
        last_name="Admin",
        requires_password_reset=True,
    )

    db.add(admin_user)
    await db.commit()

    return TEMP_ADMIN_EMAIL, temp_password


__all__ = [
    "TEMP_ADMIN_EMAIL",
    "TEMP_ADMIN_USERNAME",
    "check_admin_exists",
    "create_initial_admin",
]
