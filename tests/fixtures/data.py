"""Test data factories, context classes, and domain helpers."""

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from httpx import AsyncClient
from polyfactory.factories.pydantic_factory import ModelFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import VolunteerRegisterSchema
from app.core.services.encryption import encrypt_field, hash_email
from app.db.models import Application, Opportunity, Organization, User, UserOrganizationRole
from app.opportunities.schemas import ApplicationCreate, OpportunityCreate
from app.organizations.schemas import OrganizationCreate

RoleType = Literal["volunteer", "system_admin", "organization"]


class VolunteerRegisterSchemaFactory(ModelFactory[VolunteerRegisterSchema]):
    """Factory for generating volunteer registration data."""

    __model__ = VolunteerRegisterSchema

    @classmethod
    def first_name(cls) -> str:
        return cls.__faker__.first_name()

    @classmethod
    def last_name(cls) -> str:
        return cls.__faker__.last_name()

    @classmethod
    def username(cls) -> str:
        return cls.__faker__.user_name()

    @classmethod
    def password(cls) -> str:
        base = f"{cls.__faker__.password(length=24, special_chars=True, digits=True, upper_case=True, lower_case=True)}"
        base = "".join(ch for ch in base if 0x20 <= ord(ch) <= 0x7E)
        base = base.replace("\t", "").replace("\n", "").replace("\r", "")
        base = base.strip(" ")
        if len(base) < 16:
            base = (base + "A1!aA1!aA1!aA1!a")[:16]
        if len(base) > 64:
            base = base[:64]
        if base.strip(" ") == "":
            base = "A1!aA1!aA1!aA1!a"
        return base


# Backwards compatibility alias
RegisterSchemaFactory = VolunteerRegisterSchemaFactory


class OrganizationCreateFactory(ModelFactory[OrganizationCreate]):
    """Factory for generating organization creation data."""

    __model__ = OrganizationCreate

    @classmethod
    def username(cls) -> str:
        return cls.__faker__.user_name()


class OpportunityCreateFactory(ModelFactory[OpportunityCreate]):
    """Factory for generating opportunity creation data."""

    __model__ = OpportunityCreate


class ApplicationCreateFactory(ModelFactory[ApplicationCreate]):
    """Factory for generating application creation data."""

    __model__ = ApplicationCreate


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user with credentials and tokens."""

    id: UUID
    first_name: str | None
    last_name: str | None
    email: str
    username: str
    password: str
    tokens: dict[str, str]
    role: str

    @property
    def auth_header(self) -> dict[str, str]:
        """Return Authorization header for API requests."""
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}


@dataclass
class OrganizationContext:
    """Represents an organization with its admin for testing."""

    organization: Organization
    admin: AuthenticatedUser
    admin_user: User


@dataclass
class OpportunityContext:
    """Represents an opportunity with its organization context for testing."""

    opportunity: Opportunity
    organization: OrganizationContext


async def register_user(
    client: AsyncClient,
    role: RoleType = "volunteer",
    email: str | None = None,
    password: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
) -> AuthenticatedUser:
    """Register a new volunteer user."""
    data = VolunteerRegisterSchemaFactory.build()
    email = email or data.email
    password = password or data.password.get_secret_value()
    first_name = first_name or data.first_name
    last_name = last_name or data.last_name
    username = username or data.username

    form_data: dict[str, str] = {
        "email": email,
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
        "username": username,
    }
    csrf_token = client.cookies.get("csrf_token")
    if csrf_token:
        form_data["csrf_token"] = csrf_token

    response = await client.post(
        "/auth/register/volunteer",
        data=form_data,
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 303), f"Registration failed: {response.status_code}"
    access_token = response.cookies.get("access_token") or ""
    return AuthenticatedUser(
        id=UUID(int=0),  # ID fetched from DB if needed
        first_name=first_name,
        last_name=last_name,
        email=email,
        username=username,
        password=password,
        tokens={"access_token": access_token},
        role=role,
    )


async def login_user(client: AsyncClient, email: str, password: str, account_type: str = "volunteer") -> dict[str, str]:
    """Login a user and return tokens from cookies."""
    form_data: dict[str, str] = {"email": email, "password": password, "account_type": account_type}
    csrf_token = client.cookies.get("csrf_token")
    if csrf_token:
        form_data["csrf_token"] = csrf_token

    response = await client.post(
        "/auth/login",
        data=form_data,
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 303), f"Login failed: {response.status_code}"
    access_token = response.cookies.get("access_token") or ""
    return {"access_token": access_token}


async def register_and_login(
    client: AsyncClient,
    role: RoleType = "volunteer",
    email: str | None = None,
    password: str | None = None,
    username: str | None = None,
) -> AuthenticatedUser:
    """Register and login a user, returning full AuthenticatedUser."""
    user = await register_user(client, role, email, password, username=username)
    # If registration didn't set cookies, login separately
    if not user.tokens.get("access_token"):
        user.tokens = await login_user(client, user.email, user.password)
    return user


async def get_user_from_db(db: AsyncSession, email: str) -> User:
    """Get a user from the database by email hash."""
    result = await db.execute(select(User).where(User.email_hash == hash_email(email)))
    user = result.scalar_one_or_none()
    assert user is not None, f"User with email {email} not found"
    return user


async def create_organization_db(
    db: AsyncSession,
    name: str | None = None,
    username: str | None = None,
    description: str | None = None,
) -> Organization:
    """Create a test organization directly in the database."""
    data = OrganizationCreateFactory.build()
    org = Organization(
        name=name or data.name,
        username=username or data.username,
        description=description or data.description,
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


async def add_user_to_organization(
    db: AsyncSession,
    user_id: UUID,
    organization_id: UUID,
    role: str = "member",
) -> UserOrganizationRole:
    """Add a user to an organization with specified role."""
    user_org_role = UserOrganizationRole(user_id=user_id, organization_id=organization_id, role=role)
    db.add(user_org_role)
    await db.commit()
    await db.refresh(user_org_role)
    return user_org_role


async def create_organization_with_admin(
    client: AsyncClient,
    db: AsyncSession,
    org_name: str | None = None,
) -> OrganizationContext:
    """Create an organization with an admin user - full setup."""
    # First register a volunteer who will become org admin
    admin = await register_and_login(client, role="volunteer")
    admin_user = await get_user_from_db(db, admin.email)

    # Create org directly in DB with auth fields
    org = await create_organization_db(db, name=org_name)

    # Add user as org admin
    await add_user_to_organization(db, admin_user.id, org.id, role="admin")
    return OrganizationContext(organization=org, admin=admin, admin_user=admin_user)


async def create_opportunity_db(
    db: AsyncSession,
    organization_id: UUID,
    posted_by: UUID,
    title: str | None = None,
    description: str | None = None,
    location: str | None = None,
    *,
    is_open: bool = True,
) -> Opportunity:
    """Create a test opportunity directly in the database."""
    data = OpportunityCreateFactory.build()
    opp = Opportunity(
        title=title or data.title,
        description=description or data.description,
        location=location or data.location,
        organization_id=organization_id,
        posted_by=posted_by,
        is_open=is_open,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


async def create_opportunity_with_org(
    client: AsyncClient,
    db: AsyncSession,
    title: str | None = None,
    *,
    is_open: bool = True,
) -> OpportunityContext:
    """Create an opportunity with full organization context."""
    org_ctx = await create_organization_with_admin(client, db)
    opp = await create_opportunity_db(
        db,
        organization_id=org_ctx.organization.id,
        posted_by=org_ctx.admin_user.id,
        title=title,
        is_open=is_open,
    )
    return OpportunityContext(opportunity=opp, organization=org_ctx)


async def create_application_db(
    db: AsyncSession,
    opportunity_id: UUID,
    volunteer_id: UUID,
    message: str | None = None,
    app_status: str = "pending",
) -> Application:
    """Create a test application directly in the database."""
    data = ApplicationCreateFactory.build()
    app_obj = Application(
        opportunity_id=opportunity_id,
        volunteer_id=volunteer_id,
        message_ciphertext=encrypt_field(message or data.message),
        status=app_status,
    )
    db.add(app_obj)
    await db.commit()
    await db.refresh(app_obj)
    return app_obj


@dataclass
class FixtureContext:
    """Single context object with lazy-loaded resources.

    Replaces multiple individual fixtures with on-demand resource creation.
    """

    client: AsyncClient
    db: AsyncSession
    _volunteers: dict[str, AuthenticatedUser] = field(default_factory=dict)
    _orgs: dict[str, OrganizationContext] = field(default_factory=dict)
    _opps: dict[str, OpportunityContext] = field(default_factory=dict)

    async def volunteer(self, key: str = "default") -> AuthenticatedUser:
        """Get or create a volunteer user."""
        if key not in self._volunteers:
            self._volunteers[key] = await register_and_login(self.client, role="volunteer")
        return self._volunteers[key]

    async def organization(self, key: str = "default") -> OrganizationContext:
        """Get or create an organization with admin."""
        if key not in self._orgs:
            self._orgs[key] = await create_organization_with_admin(self.client, self.db)
        return self._orgs[key]

    async def opportunity(self, key: str = "default", **kwargs: Any) -> OpportunityContext:
        """Get or create an opportunity with organization context."""
        if key not in self._opps:
            self._opps[key] = await create_opportunity_with_org(self.client, self.db, **kwargs)
        return self._opps[key]

    async def create_volunteers(self, count: int) -> list[AuthenticatedUser]:
        """Create multiple volunteers."""
        volunteers = []
        for i in range(count):
            vol = await register_and_login(self.client, role="volunteer")
            self._volunteers[f"batch_{i}"] = vol
            volunteers.append(vol)
        return volunteers

    async def create_opportunities(
        self,
        org_context: OrganizationContext,
        count: int,
    ) -> list[Opportunity]:
        """Create multiple opportunities for an organization."""
        results = []
        for _ in range(count):
            opp = await create_opportunity_db(
                self.db,
                organization_id=org_context.organization.id,
                posted_by=org_context.admin_user.id,
            )
            results.append(opp)
        return results
