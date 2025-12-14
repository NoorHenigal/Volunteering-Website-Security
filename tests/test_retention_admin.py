"""Tests for retention anonymization admin endpoint."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, Opportunity, Organization, User
from tests.fixtures.api import APIHelper
from tests.fixtures.data import (
    AuthenticatedUser,
    create_application_db,
    create_organization_db,
    get_user_from_db,
    register_and_login,
)


async def _create_system_admin(client: AsyncClient, db: AsyncSession) -> AuthenticatedUser:
    """Create a system_admin user and return an authenticated context."""
    admin = await register_and_login(client, role="system_admin")
    db_user = await get_user_from_db(db, admin.email)
    db_user.role = "system_admin"
    await db.commit()
    await db.refresh(db_user)

    resp = await client.post(
        "/auth/login",
        json={"email": admin.email, "password": admin.password, "account_type": "volunteer"},
    )
    tokens: dict[str, str] = resp.json()
    admin.tokens = tokens
    return admin


@pytest.mark.anyio
async def test_retention_endpoint_requires_auth(api: APIHelper) -> None:
    """Anonymous callers should be rejected."""
    await api.unauthorized("POST", "/admin/retention/anonymize")


@pytest.mark.anyio
async def test_retention_endpoint_requires_system_admin(api: APIHelper, client: AsyncClient) -> None:
    """Non-admin callers should be rejected."""
    user = await register_and_login(client, role="volunteer")
    await api.forbidden("POST", "/admin/retention/anonymize", auth=user)


@pytest.mark.anyio
async def test_retention_anonymizes_deactivated_users_and_orgs(
    api: APIHelper,
    client: AsyncClient,
    test_db: AsyncSession,
) -> None:
    """Anonymization should run only on inactive entities older than the cutoff."""
    admin = await _create_system_admin(client, test_db)

    cutoff = datetime.now(UTC) - timedelta(days=90)

    u = await register_and_login(client, role="volunteer")
    db_u = await get_user_from_db(test_db, u.email)
    await test_db.execute(
        update(User).where(User.id == db_u.id).values(is_active=False, updated_at=cutoff - timedelta(days=1))
    )

    org = await create_organization_db(test_db, name="To Be Deleted", username="tbd")
    await test_db.execute(
        update(Organization)
        .where(Organization.id == org.id)
        .values(is_active=False, updated_at=cutoff - timedelta(days=1))
    )

    opp = Opportunity(
        title="Test",
        description="Desc",
        organization_id=org.id,
        posted_by=db_u.id,
        is_open=True,
    )
    test_db.add(opp)
    await test_db.commit()
    await test_db.refresh(opp)

    app = await create_application_db(test_db, opportunity_id=opp.id, volunteer_id=db_u.id, message="secret")

    result = await api.ok("POST", "/admin/retention/anonymize", auth=admin)
    assert result["anonymized_users"] >= 1
    assert result["anonymized_organizations"] >= 1

    refreshed_user = await test_db.get(User, db_u.id)
    assert refreshed_user is not None
    assert refreshed_user.username.startswith("deleted-user-")
    assert refreshed_user.email.endswith("@example.invalid") or refreshed_user.email.endswith("@example.com")
    assert refreshed_user.profile_visibility == "private"
    assert refreshed_user.searchable is False
    assert refreshed_user.show_email is False

    refreshed_org = await test_db.get(Organization, org.id)
    assert refreshed_org is not None
    assert refreshed_org.username.startswith("deleted-org-")
    assert refreshed_org.name == "Deleted Organization"
    assert refreshed_org.banner is None
    assert refreshed_org.logo is None

    app_row = await test_db.get(Application, app.id)
    assert app_row is not None
    assert app_row.message is None


@pytest.mark.anyio
async def test_retention_does_not_anonymize_recent_deactivations(
    api: APIHelper,
    client: AsyncClient,
    test_db: AsyncSession,
) -> None:
    """Recent deactivations (within retention window) should not be anonymized."""
    admin = await _create_system_admin(client, test_db)

    cutoff = datetime.now(UTC) - timedelta(days=90)

    u = await register_and_login(client, role="volunteer")
    db_u = await get_user_from_db(test_db, u.email)
    await test_db.execute(
        update(User).where(User.id == db_u.id).values(is_active=False, updated_at=cutoff + timedelta(days=1))
    )

    org = await create_organization_db(test_db, name="Recent", username="recent")
    await test_db.execute(
        update(Organization)
        .where(Organization.id == org.id)
        .values(is_active=False, updated_at=cutoff + timedelta(days=1))
    )
    await test_db.commit()

    await api.ok("POST", "/admin/retention/anonymize", auth=admin)

    refreshed_user = await test_db.get(User, db_u.id)
    assert refreshed_user is not None
    assert refreshed_user.username == db_u.username

    refreshed_org = await test_db.get(Organization, org.id)
    assert refreshed_org is not None
    assert refreshed_org.username == "recent"
