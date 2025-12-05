"""Schemathesis hooks for API testing."""

from __future__ import annotations

import logging
import re
import secrets
import string
import warnings
from typing import TYPE_CHECKING, Any

import requests
import schemathesis
from hypothesis import strategies as st

# Suppress HypothesisWarning about overriding email format
warnings.filterwarnings("ignore", message="Overriding standard format")

if TYPE_CHECKING:
    from hypothesis.strategies import SearchStrategy

# Schemathesis hook context type (opaque)
type HookContext = object

logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8000"

VALID_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.0-9A-Z^_`a-z|~]+$")
VALID_HEADER_VALUE = re.compile(r"^[\x20-\x7E\t]*$")

# Custom email strategy for Pydantic compatibility
schemathesis.openapi.format(
    "email",
    st.builds(
        lambda local, domain: f"{local}@{domain}.com",
        local=st.text(alphabet=string.ascii_lowercase + string.digits, min_size=3, max_size=10),
        domain=st.text(alphabet=string.ascii_lowercase, min_size=3, max_size=8),
    ),
)

_test_data: dict[str, Any] = {}


def _random_string(length: int = 8) -> str:
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def _setup_test_data() -> None:
    """Create test users, organization, opportunity, and application."""
    if _test_data.get("initialized"):
        return

    try:
        # Register volunteer
        vol_suffix = _random_string()
        vol_data = {
            "email": f"vol_{vol_suffix}@example.com",
            "password": "TestPass123!",
            "role": "volunteer",
            "first_name": "Test",
            "last_name": "Volunteer",
            "username": f"vol_{vol_suffix}",
        }
        requests.post(f"{BASE_URL}/api/auth/register", json=vol_data, timeout=10)
        vol_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": vol_data["email"], "password": vol_data["password"]},
            timeout=10,
        )
        _test_data["vol_token"] = vol_login.json().get("access_token")
        _test_data["vol_user"] = vol_data

        # Register org user
        org_suffix = _random_string()
        org_data = {
            "email": f"org_{org_suffix}@example.com",
            "password": "TestPass123!",
            "role": "organization",
            "first_name": "Test",
            "last_name": "Organization",
            "username": f"org_{org_suffix}",
        }
        requests.post(f"{BASE_URL}/api/auth/register", json=org_data, timeout=10)
        org_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": org_data["email"], "password": org_data["password"]},
            timeout=10,
        )
        _test_data["org_token"] = org_login.json().get("access_token")
        _test_data["org_user"] = org_data

        # Create organization
        org_resp = requests.post(
            f"{BASE_URL}/api/organizations",
            json={"name": f"TestOrg_{_random_string()}", "description": "Test"},
            headers={"Authorization": f"Bearer {_test_data['org_token']}"},
            timeout=10,
        )
        _test_data["organization_id"] = org_resp.json().get("id")

        # Create opportunity
        opp_resp = requests.post(
            f"{BASE_URL}/api/opportunities",
            json={
                "title": f"TestOpp_{_random_string()}",
                "description": "Test",
                "organization_id": _test_data["organization_id"],
            },
            headers={"Authorization": f"Bearer {_test_data['org_token']}"},
            timeout=10,
        )
        _test_data["opportunity_id"] = opp_resp.json().get("id")

        # Create application
        app_resp = requests.post(
            f"{BASE_URL}/api/opportunities/{_test_data['opportunity_id']}/apply",
            json={"message": "Test"},
            headers={"Authorization": f"Bearer {_test_data['vol_token']}"},
            timeout=10,
        )
        _test_data["application_id"] = app_resp.json().get("id")
        _test_data["initialized"] = True

    except requests.RequestException as e:
        logger.warning("Test data setup failed: %s", e)


def _get_token(path: str, method: str) -> str | None:
    """Get appropriate auth token based on endpoint."""
    _setup_test_data()

    # Org token needed for: create org, create opp, update app status
    if method == "POST" and ("/api/organizations" in path or path == "/api/opportunities"):
        return _test_data.get("org_token")
    if method == "PUT" and "/api/applications/" in path:
        return _test_data.get("org_token")

    return _test_data.get("vol_token")


@(
    schemathesis.auth()
    .skip_for(path="/health")
    .skip_for(path="/api/auth/register")
    .skip_for(path="/api/auth/login")
    .skip_for(path="/api/auth/logout")
)
class DynamicAuth:
    """JWT authentication for protected endpoints."""

    def get(self, case: object, ctx: object) -> str | None:
        """Get authentication token for the request."""
        path = getattr(ctx, "path", "") or getattr(case, "path", "") or ""
        method = getattr(case, "method", "GET")
        return _get_token(path, method)

    def set(self, case: object, data: str | None, ctx: object) -> None:
        """Apply authentication token to the request."""
        del ctx  # Unused
        if data:
            headers = getattr(case, "headers", None) or {}
            headers["Authorization"] = f"Bearer {data}"
            case.headers = headers  # type: ignore[attr-defined]


@schemathesis.hook
def filter_headers(_ctx: HookContext, headers: dict[str, Any] | None) -> bool:
    """Filter invalid HTTP headers."""
    if not headers:
        return True
    return all(VALID_HEADER_NAME.match(k) and VALID_HEADER_VALUE.match(str(v)) for k, v in headers.items())


@schemathesis.hook
def map_headers(_ctx: HookContext, headers: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove invalid headers."""
    if not headers:
        return None
    return {k: v for k, v in headers.items() if VALID_HEADER_NAME.match(k) and VALID_HEADER_VALUE.match(str(v))} or None


@schemathesis.hook
def before_generate_path_parameters(_ctx: HookContext, strategy: SearchStrategy[Any]) -> SearchStrategy[Any]:
    """Inject real IDs into path parameters."""
    _setup_test_data()

    def fix(params: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(params, dict):
            return params

        # Fix minLength and inject real IDs
        if "username" in params:
            params["username"] = _test_data.get("vol_user", {}).get("username", "testuser")
        if "slug" in params:
            params["slug"] = _test_data.get("vol_user", {}).get("username", "testuser")
        if "organization_id" in params:
            params["organization_id"] = _test_data.get("organization_id", params["organization_id"])
        if "opportunity_id" in params:
            params["opportunity_id"] = _test_data.get("opportunity_id", params["opportunity_id"])
        if "application_id" in params:
            params["application_id"] = _test_data.get("application_id", params["application_id"])

        return params

    return strategy.map(fix)


@schemathesis.hook
def filter_body(_ctx: HookContext, body: dict[str, Any] | None) -> bool:
    """Filter whitespace-only name/title fields."""
    if not isinstance(body, dict):
        return True
    name = body.get("name")
    title = body.get("title")
    if name is not None and isinstance(name, str) and not name.strip():
        return False
    return not (title is not None and isinstance(title, str) and not title.strip())


@schemathesis.hook
def map_body(_ctx: HookContext, body: dict[str, Any] | None) -> dict[str, Any] | None:
    """Inject real org ID and generate unique registration data."""
    if not isinstance(body, dict):
        return body

    _setup_test_data()

    if "organization_id" in body:
        body["organization_id"] = _test_data.get("organization_id", body["organization_id"])

    # Unique registration data
    if "email" in body and "password" in body and "role" in body:
        suffix = _random_string(16)
        body["email"] = f"test_{suffix}@example.com"
        if "username" in body:
            body["username"] = f"user_{suffix}"

    return body
