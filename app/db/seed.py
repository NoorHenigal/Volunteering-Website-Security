"""Database seeding utilities for demo data generation.

This module provides functionality to seed the database with realistic demo data
using the Faker library. All data is dynamically generated - no hardcoded values.
The seeding is idempotent and will only run once.
"""

import logging

from faker import Faker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import hash_password
from app.db.models import Application, Opportunity, Organization, User, UserOrganizationRole
from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)

# Marker organization name to check if demo data already exists
DEMO_MARKER = "Demo Data Marker Org"

# Seed for reproducible data
FAKER_SEED = 42


async def seed_demo_data() -> None:
    """Seed the database with demo data if it doesn't already exist.

    This function is idempotent - it checks for existing demo data and skips
    seeding if found. All operations are performed in a single transaction.
    All data is dynamically generated using Faker.
    """
    async with AsyncSessionLocal() as session:
        # Check if demo data already exists
        result = await session.execute(select(Organization).where(Organization.name == DEMO_MARKER))
        if result.scalar_one_or_none():
            log.info("✓ Demo data already exists, skipping seeding")
            return

        log.info("Seeding demo data...")

        try:
            # Initialize Faker with seed for reproducibility
            fake = Faker()
            Faker.seed(FAKER_SEED)

            # Create entities in order of dependencies
            orgs = await _create_organizations(session, fake)
            users = await _create_users(session, fake)
            await _create_user_org_roles(session, fake, users, orgs)
            opportunities = await _create_opportunities(session, fake, users, orgs)
            await _create_applications(session, fake, users, opportunities)

            # Commit all changes
            await session.commit()
            log.info("✓ Demo data seeded successfully")
            log.info(
                "  Created: %d organizations, %d users, %d opportunities",
                len(orgs),
                len(users),
                len(opportunities),
            )

        except Exception:
            await session.rollback()
            log.exception("Failed to seed demo data")
            raise


async def _create_organizations(session: AsyncSession, fake: Faker) -> list[Organization]:
    """Create demo organizations with dynamic data.

    Args:
        session: Database session
        fake: Faker instance

    Returns:
        List of created organizations
    """
    organizations = [
        # Marker organization for idempotency check
        Organization(
            name=DEMO_MARKER,
            description="Internal marker - do not delete",
        ),
    ]

    # Create 4-6 organizations with dynamic names and descriptions
    num_orgs = fake.random_int(min=4, max=6)
    for _ in range(num_orgs):
        org = Organization(
            name=fake.company(),
            description=fake.catch_phrase() + ". " + fake.bs().capitalize() + ".",
        )
        organizations.append(org)

    session.add_all(organizations)
    await session.flush()  # Get IDs without committing
    return organizations


async def _create_users(session: AsyncSession, fake: Faker) -> list[User]:
    """Create demo users (volunteers and organization admins) with dynamic data.

    Args:
        session: Database session
        fake: Faker instance

    Returns:
        List of created users
    """
    # Default password for all demo users
    default_password = hash_password("demo123")

    users = []

    # Create 8-12 volunteers
    num_volunteers = fake.random_int(min=8, max=12)
    for _ in range(num_volunteers):
        first_name = fake.first_name()
        last_name = fake.last_name()
        username = fake.unique.user_name()

        user = User(
            email=fake.unique.email(),
            password_hash=default_password,
            role="volunteer",
            first_name=first_name,
            last_name=last_name,
            username=username,
        )
        users.append(user)

    # Create 4-6 organization admins
    num_org_users = fake.random_int(min=4, max=6)
    for _ in range(num_org_users):
        first_name = fake.first_name()
        last_name = fake.last_name()
        username = fake.unique.user_name()

        user = User(
            email=fake.unique.email(),
            password_hash=default_password,
            role="organization",
            first_name=first_name,
            last_name=last_name,
            username=username,
        )
        users.append(user)

    session.add_all(users)
    await session.flush()

    log.info("  Demo user credentials: email=<any demo user email>, password=demo123")
    return users


async def _create_user_org_roles(
    session: AsyncSession,
    fake: Faker,
    users: list[User],
    orgs: list[Organization],
) -> None:
    """Create user-organization role relationships dynamically.

    Args:
        session: Database session
        fake: Faker instance
        users: List of users
        orgs: List of organizations
    """
    # Get organization users
    org_users = [u for u in users if u.role == "organization"]

    # Skip the marker org (first one)
    real_orgs = orgs[1:]

    roles = []

    # Assign 1-2 admins per organization
    for i, org in enumerate(real_orgs):
        # Primary admin
        primary_admin = org_users[i % len(org_users)]
        roles.append(
            UserOrganizationRole(
                user_id=primary_admin.id,
                organization_id=org.id,
                role="admin",
            )
        )

        # Randomly add a second admin
        if fake.boolean(chance_of_getting_true=50) and len(org_users) > 1:
            secondary_admin = org_users[(i + 1) % len(org_users)]
            if secondary_admin.id != primary_admin.id:
                roles.append(
                    UserOrganizationRole(
                        user_id=secondary_admin.id,
                        organization_id=org.id,
                        role="admin",
                    )
                )

    session.add_all(roles)
    await session.flush()


async def _create_opportunities(
    session: AsyncSession,
    fake: Faker,
    users: list[User],
    orgs: list[Organization],
) -> list[Opportunity]:
    """Create demo opportunities with dynamic data.

    Args:
        session: Database session
        fake: Faker instance
        users: List of users
        orgs: List of organizations

    Returns:
        List of created opportunities
    """
    org_users = [u for u in users if u.role == "organization"]
    real_orgs = orgs[1:]  # Skip marker org

    opportunities = []

    # Create 8-15 opportunities
    num_opps = fake.random_int(min=8, max=15)

    for i in range(num_opps):
        org = real_orgs[i % len(real_orgs)]
        poster = org_users[i % len(org_users)]

        opp = Opportunity(
            title=fake.job(),
            description=fake.paragraph(nb_sentences=3),
            location=fake.city(),
            posted_by=poster.id,
            organization_id=org.id,
            is_open=fake.boolean(chance_of_getting_true=80),  # 80% open
        )
        opportunities.append(opp)

    session.add_all(opportunities)
    await session.flush()
    return opportunities


async def _create_applications(
    session: AsyncSession,
    fake: Faker,
    users: list[User],
    opportunities: list[Opportunity],
) -> None:
    """Create demo applications with various statuses dynamically.

    Args:
        session: Database session
        fake: Faker instance
        users: List of users
        opportunities: List of opportunities
    """
    volunteers = [u for u in users if u.role == "volunteer"]

    applications = []
    statuses = ["pending", "accepted", "rejected", "withdrawn"]

    # Create 2-4 applications per opportunity
    app_count = 0
    for opp in opportunities:
        num_apps = fake.random_int(min=2, max=4)

        for _ in range(num_apps):
            volunteer = volunteers[app_count % len(volunteers)]

            # Randomly select status (weighted toward pending and accepted)
            status = fake.random_element(elements=statuses)

            # 50% chance of having a message
            message = fake.sentence(nb_words=10) if fake.boolean() else None

            app = Application(
                opportunity_id=opp.id,
                volunteer_id=volunteer.id,
                status=status,
                message=message,
            )
            applications.append(app)
            app_count += 1

    session.add_all(applications)
    await session.flush()


__all__ = ["seed_demo_data"]
