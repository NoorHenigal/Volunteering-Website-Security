"""Schemathesis hooks."""

import logging
import re
import secrets
import string
import warnings
from typing import TYPE_CHECKING, Any

import requests
import schemathesis
from hypothesis import strategies as st

warnings.filterwarnings("ignore", message="Overriding standard format")

if TYPE_CHECKING:
    from hypothesis.strategies import SearchStrategy

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
    """Create test users, organization, opportunity, and application via UI forms."""
    if _test_data.get("initialized"):
        return

    session = requests.Session()

    try:
        # Get CSRF token first
        session.get(f"{BASE_URL}/auth/login", timeout=10)
        csrf_token = session.cookies.get("csrf_token", "")

        # Register volunteer via form
        vol_suffix = _random_string()
        vol_data = {
            "email": f"vol_{vol_suffix}@example.com",
            "password": "TestPass123!TestPass",
            "first_name": "Test",
            "last_name": "Volunteer",
            "username": f"vol_{vol_suffix}",
            "csrf_token": csrf_token,
        }
        resp = session.post(
            f"{BASE_URL}/auth/register/volunteer",
            data=vol_data,
            headers={"Accept": "text/html"},
            allow_redirects=False,
            timeout=10,
        )
        _test_data["vol_cookies"] = dict(session.cookies)
        _test_data["vol_user"] = vol_data
        logger.info("Volunteer registered: %s (status=%d)", vol_data["username"], resp.status_code)

        # Register org user via form (creates org automatically)
        session2 = requests.Session()
        session2.get(f"{BASE_URL}/auth/login", timeout=10)
        csrf_token2 = session2.cookies.get("csrf_token", "")

        org_suffix = _random_string()
        org_data = {
            "email": f"org_{org_suffix}@example.com",
            "password": "TestPass123!TestPass",
            "username": f"org_{org_suffix}",
            "name": f"TestOrg_{org_suffix}",
            "csrf_token": csrf_token2,
        }
        resp = session2.post(
            f"{BASE_URL}/auth/register/organization",
            data=org_data,
            headers={"Accept": "text/html"},
            allow_redirects=False,
            timeout=10,
        )
        _test_data["org_cookies"] = dict(session2.cookies)
        _test_data["org_user"] = org_data
        logger.info("Organization registered: %s (status=%d)", org_data["username"], resp.status_code)

        # Get organization ID from database by fetching the org page
        org_page = session2.get(
            f"{BASE_URL}/{org_data['username']}",
            headers={"Accept": "text/html"},
            timeout=10,
        )
        # Extract org ID from page content (look for organization_id in forms)
        org_id_match = re.search(r'organization_id["\s:=]+([a-f0-9-]{36})', org_page.text, re.IGNORECASE)
        if org_id_match:
            _test_data["organization_id"] = org_id_match.group(1)
            logger.info("Found organization_id: %s", _test_data["organization_id"])
        else:
            # Try to get from opportunities page
            opps_page = session2.get(f"{BASE_URL}/opportunities", headers={"Accept": "text/html"}, timeout=10)
            org_id_match = re.search(r'organization_id["\s:=]+([a-f0-9-]{36})', opps_page.text, re.IGNORECASE)
            if org_id_match:
                _test_data["organization_id"] = org_id_match.group(1)
                logger.info("Found organization_id from opps page: %s", _test_data["organization_id"])

        # Create opportunity via form if we have org ID
        if _test_data.get("organization_id"):
            opp_data = {
                "title": f"TestOpp_{_random_string()}",
                "description": "Test opportunity description",
                "organization_id": _test_data["organization_id"],
                "location": "Test Location",
                "csrf_token": session2.cookies.get("csrf_token", csrf_token2),
            }
            resp = session2.post(
                f"{BASE_URL}/opportunities",
                data=opp_data,
                headers={"Accept": "text/html"},
                allow_redirects=False,
                timeout=10,
            )
            # Extract opportunity ID from redirect location
            location = resp.headers.get("location", "")
            opp_id_match = re.search(r"/opportunities/([a-f0-9-]{36})", location)
            if opp_id_match:
                _test_data["opportunity_id"] = opp_id_match.group(1)
                logger.info("Created opportunity: %s", _test_data["opportunity_id"])

        # Apply to opportunity as volunteer
        if _test_data.get("opportunity_id"):
            app_data = {
                "message": "Test application message",
                "csrf_token": session.cookies.get("csrf_token", csrf_token),
            }
            resp = session.post(
                f"{BASE_URL}/opportunities/{_test_data['opportunity_id']}/apply",
                data=app_data,
                headers={"Accept": "text/html"},
                allow_redirects=False,
                timeout=10,
            )
            logger.info("Applied to opportunity (status=%d)", resp.status_code)
            # Application ID would need to be extracted from DB or page, using placeholder
            _test_data["application_id"] = "00000000-0000-0000-0000-000000000000"

        _test_data["initialized"] = True
        logger.info("Test data setup complete")

    except requests.RequestException as e:
        logger.warning("Test data setup failed: %s", e)


def _get_cookies(path: str, method: str) -> dict[str, str]:
    """Get appropriate auth cookies based on endpoint."""
    _setup_test_data()

    empty_cookies: dict[str, str] = {}
    org_cookies: dict[str, str] = _test_data.get("org_cookies") or empty_cookies
    vol_cookies: dict[str, str] = _test_data.get("vol_cookies") or empty_cookies

    # Org cookies needed for: create opp, update app status, org management
    if method == "POST" and ("/organizations" in path or path == "/opportunities"):
        return org_cookies
    if method == "PUT" and "/applications/" in path:
        return org_cookies
    if method in ("PUT", "DELETE") and "/organizations/" in path:
        return org_cookies

    return vol_cookies


@(
    schemathesis.auth()
    .skip_for(path="/health")
    .skip_for(path="/auth/register/volunteer")
    .skip_for(path="/auth/register/organization")
    .skip_for(path="/auth/login")
    .skip_for(path="/auth/logout")
)
class CookieAuth:
    """Cookie-based authentication for protected endpoints."""

    def get(self, case: object, ctx: object) -> dict[str, str]:
        """Get authentication cookies for the request."""
        path = getattr(ctx, "path", "") or getattr(case, "path", "") or ""
        method = getattr(case, "method", "GET")
        return _get_cookies(path, method)

    def set(self, case: object, data: dict[str, str], ctx: object) -> None:
        """Apply authentication cookies to the request."""
        del ctx  # Unused
        if data:
            cookies = getattr(case, "cookies", None) or {}
            cookies.update(data)
            case.cookies = cookies  # type: ignore[attr-defined]


@schemathesis.hook
def filter_headers(_ctx: HookContext, headers: dict[str, Any] | None) -> bool:
    """Filter invalid HTTP headers and null authorization values."""
    if not headers:
        return True
    # Filter out null/None authorization header values
    auth = headers.get("authorization")
    if auth is None or (isinstance(auth, str) and not auth.strip()):
        return False
    return all(VALID_HEADER_NAME.match(k) and VALID_HEADER_VALUE.match(str(v)) for k, v in headers.items())


@schemathesis.hook
def map_headers(_ctx: HookContext, headers: dict[str, Any] | None) -> dict[str, Any] | None:
    """Remove invalid headers and add Accept: text/html for endpoints."""
    if not headers:
        headers = {}
    headers = {k: v for k, v in headers.items() if VALID_HEADER_NAME.match(k) and VALID_HEADER_VALUE.match(str(v))}
    headers["Accept"] = "text/html"
    return headers or None


@schemathesis.hook
def before_generate_path_parameters(_ctx: HookContext, strategy: SearchStrategy[Any]) -> SearchStrategy[Any]:
    """Inject real IDs into path parameters."""
    _setup_test_data()

    def fix(params: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(params, dict):
            return params

        if "username" in params:
            params["username"] = _test_data.get("vol_user", {}).get("username", "testuser")
        if "slug" in params:
            params["slug"] = _test_data.get("vol_user", {}).get("username", "testuser")
        if "organization_id" in params and _test_data.get("organization_id"):
            params["organization_id"] = _test_data["organization_id"]
        if "opportunity_id" in params and _test_data.get("opportunity_id"):
            params["opportunity_id"] = _test_data["opportunity_id"]
        if "application_id" in params and _test_data.get("application_id"):
            params["application_id"] = _test_data["application_id"]

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

    if "organization_id" in body and _test_data.get("organization_id"):
        body["organization_id"] = _test_data["organization_id"]

    # Unique registration data
    if "email" in body and "password" in body:
        suffix = _random_string(16)
        body["email"] = f"test_{suffix}@example.com"
        if "username" in body:
            body["username"] = f"user_{suffix}"
        # Ensure password meets requirements
        if "password" in body:
            body["password"] = "TestPass123!TestPass"  # noqa: S105

    return body
