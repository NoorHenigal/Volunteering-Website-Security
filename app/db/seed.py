"""Database seeding utilities for demo data generation."""

import logging

from faker import Faker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import hash_password
from app.db.models import Application, Follow, Opportunity, Organization, User, UserOrganizationRole
from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)

FAKER_SEED = 42


async def seed_demo_data() -> None:
    """Seed the database with demo data if it doesn't already exist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Organization).limit(1))
        if result.scalar_one_or_none():
            log.info("✓ Demo data already exists, skipping seeding")
            return

        log.info("Seeding demo data...")

        try:
            fake = Faker()
            Faker.seed(FAKER_SEED)
            users = await _create_users(session, fake)

            orgs, used_user_count = await _create_organizations_with_sequence(session, fake, users)
            opportunities = await _create_opportunities(session, fake, orgs)
            volunteers = users[used_user_count:]

            await _create_applications(session, fake, volunteers, opportunities)
            await _create_follows(session, fake, users)
            await session.commit()
            log.info("✓ Demo data seeded successfully")

        except Exception:
            await session.rollback()
            log.exception("Failed to seed demo data")
            raise


async def _create_users(session: AsyncSession, fake: Faker) -> list[User]:
    """Create 56 demo users (28 Male, 28 Female)."""
    default_password = hash_password("demo123")
    users = []
    visibility_sequence = ["public", "authenticated", "private"]

    males = []
    females = []

    for i in range(28):
        avatar_num = (i % 7) + 1
        first_name = fake.first_name_male()
        last_name = fake.last_name()
        username = f"{first_name}{last_name}{i + 1}"

        user = User(
            email=f"male_{i + 1}@example.com",
            password_hash=default_password,
            role="volunteer",
            first_name=first_name,
            last_name=last_name,
            username=username,
            profile_picture=f"demo-male-{avatar_num}.webp",
            bio=fake.sentence(nb_words=8),
            description=fake.paragraph(nb_sentences=2),
            profile_visibility=visibility_sequence[i % 3],
            show_email=True,
            show_organizations=True,
            searchable=True,
        )
        males.append(user)

    for i in range(28):
        avatar_num = (i % 7) + 1
        first_name = fake.first_name_female()
        last_name = fake.last_name()
        username = f"{first_name}{last_name}{i + 1}"

        user = User(
            email=f"female_{i + 1}@example.com",
            password_hash=default_password,
            role="volunteer",
            first_name=first_name,
            last_name=last_name,
            username=username,
            profile_picture=f"demo-female-{avatar_num}.webp",
            bio=fake.sentence(nb_words=8),
            description=fake.paragraph(nb_sentences=2),
            profile_visibility=visibility_sequence[i % 3],
            show_email=True,
            show_organizations=True,
            searchable=True,
        )
        females.append(user)

    for i in range(28):
        users.append(males[i])
        users.append(females[i])

    session.add_all(users)
    await session.flush()
    return users


async def _create_organizations_with_sequence(
    session: AsyncSession, fake: Faker, users: list[User]
) -> tuple[list[Organization], int]:
    """Create 18 organizations with 1-2-0 admin visibility sequence.

    Returns:
        (List[Organization], number_of_users_consumed_as_admins)
    """
    organizations = []
    user_idx = 0
    sequence = [1, 2, 0]

    for i in range(18):
        required_visible = sequence[i % 3]
        required_two_admins = 2
        num_admins = 2 if required_visible == required_two_admins else 1

        current_org_admins: list[User] = []
        is_ghost_org = required_visible == 0

        for _ in range(num_admins):
            admin = users[user_idx]
            user_idx += 1
            current_org_admins.append(admin)

        primary_admin = current_org_admins[0]
        last_name = primary_admin.last_name or "Doe"

        org_name = last_name + " Foundation" if i % 2 == 0 else "The " + last_name + " Initiative"

        slug_base = org_name.lower().replace("the ", "", 1).strip().replace(" ", "_").replace(".", "")
        org_username = slug_base

        for admin in current_org_admins:
            if is_ghost_org:
                admin.role = "organization"
                admin.username = org_username
                admin.custom_display_name = org_name
            else:
                admin.role = "volunteer"

            session.add(admin)

        banner_num = (i % 10) + 1
        org_banner = f"demo-{banner_num}.webp"

        org = Organization(
            name=org_name,
            description=fake.catch_phrase() + ". " + fake.bs().capitalize() + ".",
            username=org_username,
            banner=org_banner,
            logo=None,
        )
        session.add(org)
        await session.flush()

        for admin in current_org_admins:
            role = UserOrganizationRole(
                user_id=admin.id,
                organization_id=org.id,
                role="admin",
            )
            session.add(role)

        organizations.append(org)

    await session.flush()
    return organizations, user_idx


async def _create_opportunities(
    session: AsyncSession,
    fake: Faker,
    orgs: list[Organization],
) -> list[Opportunity]:
    """Create 18 opportunities (1 per org)."""
    opportunities = []

    for i, org in enumerate(orgs):
        result = await session.execute(
            select(UserOrganizationRole).where(
                UserOrganizationRole.organization_id == org.id, UserOrganizationRole.role == "admin"
            )
        )
        admin_role = result.scalars().first()
        if not admin_role:
            continue  # Should not happen

        banner_num = (i % 10) + 1
        opp_banner = f"demo-{banner_num}.webp"

        opp = Opportunity(
            title=fake.job(),
            description=fake.paragraph(nb_sentences=3),
            location=fake.city(),
            posted_by=admin_role.user_id,
            organization_id=org.id,
            is_open=True,
            banner=opp_banner,
        )
        opportunities.append(opp)

    session.add_all(opportunities)
    await session.flush()
    return opportunities


async def _create_applications(
    session: AsyncSession,
    fake: Faker,
    volunteers: list[User],
    opportunities: list[Opportunity],
) -> None:
    """Create applications."""
    applications = []
    statuses = ["pending", "accepted", "rejected"]

    for i, vol in enumerate(volunteers):
        start_idx = i % len(opportunities)
        for k in range(2):
            opp = opportunities[(start_idx + k) % len(opportunities)]
            app = Application(
                opportunity_id=opp.id,
                volunteer_id=vol.id,
                status=fake.random_element(statuses),
                message=fake.sentence(),
            )
            applications.append(app)

    session.add_all(applications)
    await session.flush()


async def _create_follows(session: AsyncSession, fake: Faker, users: list[User]) -> None:
    """Create follows."""
    follows = []
    created_pairs = set()

    for user in users:
        num_to_follow = (hash(user.username) % 4) + 3
        potential_targets = [u for u in users if u.id != user.id]
        targets = fake.random_elements(potential_targets, length=num_to_follow, unique=True)

        for target in targets:
            pair = (str(user.id), str(target.id))
            if pair not in created_pairs:
                created_pairs.add(pair)
                follow = Follow(follower_id=user.id, followed_id=target.id)
                follows.append(follow)

    session.add_all(follows)
    await session.flush()


__all__ = ["seed_demo_data"]
