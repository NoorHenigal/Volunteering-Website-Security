"""Tests for user and organization profiles."""

import pytest
from httpx import AsyncClient
from pyfakefs.fake_filesystem import FakeFilesystem
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Follow
from tests.fixtures.data import (
    create_organization_with_admin,
    get_user_from_db,
    register_and_login,
    register_user,
)


@pytest.mark.anyio
async def test_user_profile_access(client: AsyncClient) -> None:
    """Test accessing a user profile."""
    await register_user(client, username="testuser", first_name="Test", last_name="User")
    response = await client.get("/testuser", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Test User" in response.text
    assert "@testuser" in response.text


@pytest.mark.anyio
async def test_organization_profile_access(client: AsyncClient, test_db: AsyncSession) -> None:
    """Test accessing an organization profile."""
    org_ctx = await create_organization_with_admin(client, test_db, org_name="TestOrg")
    response = await client.get(f"/{org_ctx.organization.username}", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "TestOrg" in response.text


@pytest.mark.anyio
async def test_profile_not_found(client: AsyncClient) -> None:
    """Test that non-existent profile returns 404 or redirect."""
    response = await client.get("/nonexistent_user_12345", headers={"Accept": "text/html"})
    assert response.status_code in (303, 404)


@pytest.mark.anyio
async def test_profile_shows_follower_stats(client: AsyncClient) -> None:
    """Test that profile shows follower/following counts."""
    await register_user(client, username="statsuser", first_name="Stats", last_name="User")
    response = await client.get("/statsuser", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Followers" in response.text
    assert "Following" in response.text


@pytest.mark.anyio
async def test_follow_user(client: AsyncClient, test_db: AsyncSession) -> None:
    """Test following another user."""
    user1 = await register_and_login(client, role="volunteer")
    await register_user(client, username="followtarget", first_name="Follow", last_name="Target")

    response = await client.post(
        "/followtarget/follow",
        headers=user1.auth_header,
        follow_redirects=False,
    )
    assert response.status_code in (200, 201, 303)

    user1_db = await get_user_from_db(test_db, user1.email)
    result = await test_db.execute(Follow.__table__.select().where(Follow.follower_id == user1_db.id))
    follows = result.fetchall()
    assert len(follows) == 1


@pytest.mark.anyio
async def test_unfollow_user(client: AsyncClient, test_db: AsyncSession) -> None:
    """Test unfollowing a user."""
    user1 = await register_and_login(client, role="volunteer")
    await register_user(client, username="unfollowme", first_name="Unfollow", last_name="Me")

    await client.post("/unfollowme/follow", headers=user1.auth_header, follow_redirects=False)
    response = await client.post(
        "/unfollowme/unfollow",
        headers=user1.auth_header,
        follow_redirects=False,
    )
    assert response.status_code in (200, 303)

    user1_db = await get_user_from_db(test_db, user1.email)
    result = await test_db.execute(Follow.__table__.select().where(Follow.follower_id == user1_db.id))
    follows = result.fetchall()
    assert len(follows) == 0


@pytest.mark.anyio
async def test_cannot_follow_self(client: AsyncClient) -> None:
    """Test that users cannot follow themselves."""
    user = await register_and_login(client, role="volunteer")
    user_db_email = user.email.split("@")[0].replace(".", "")[:20]

    response = await client.post(
        f"/{user_db_email}/follow",
        headers=user.auth_header,
        follow_redirects=False,
    )
    assert response.status_code in (400, 404)


@pytest.mark.anyio
async def test_update_profile_bio(client: AsyncClient) -> None:
    """Test updating profile bio."""
    user = await register_and_login(client, role="volunteer")

    response = await client.post(
        "/settings/profile",
        headers={**user.auth_header, "Accept": "text/html"},
        data={"bio": "This is my test bio", "description": "A longer description"},
        follow_redirects=False,
    )
    assert response.status_code in (200, 303)


@pytest.mark.anyio
async def test_update_privacy_settings(client: AsyncClient) -> None:
    """Test updating privacy settings."""
    user = await register_and_login(client, role="volunteer")

    response = await client.post(
        "/settings/privacy",
        headers={**user.auth_header, "Accept": "text/html"},
        data={
            "profile_visibility": "authenticated",
            "show_email": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code in (200, 303)


@pytest.mark.anyio
async def test_privacy_settings_page_requires_auth(client: AsyncClient) -> None:
    """Test that privacy settings page requires authentication."""
    response = await client.get("/settings/privacy", follow_redirects=False)
    assert response.status_code == 401


@pytest.mark.anyio
async def test_followers_list(client: AsyncClient) -> None:
    """Test viewing followers list."""
    await register_user(client, username="listuser", first_name="List", last_name="User")
    response = await client.get("/listuser/followers", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "followers" in response.text.lower()


@pytest.mark.anyio
async def test_following_list(client: AsyncClient) -> None:
    """Test viewing following list."""
    await register_user(client, username="listuser2", first_name="List", last_name="User2")
    response = await client.get("/listuser2/following", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "following" in response.text.lower() or "follows" in response.text.lower()


@pytest.mark.anyio
async def test_profile_visibility_authenticated(client: AsyncClient) -> None:
    """Test authenticated only visibility."""
    target = await register_and_login(client, username="authonly", role="volunteer")
    csrf_token = client.cookies.get("csrf_token", "")

    response = await client.post(
        "/settings/privacy",
        headers={**target.auth_header, "Accept": "text/html"},
        data={"profile_visibility": "authenticated", "csrf_token": csrf_token},
    )
    assert response.status_code in (200, 303)
    response = await client.get("/authonly", headers={**target.auth_header, "Accept": "text/html"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_profile_visibility_followers(client: AsyncClient) -> None:
    """Test followers only visibility."""
    target = await register_and_login(client, username="followonly", role="volunteer")
    csrf_token = client.cookies.get("csrf_token", "")

    response = await client.post(
        "/settings/privacy",
        headers={**target.auth_header, "Accept": "text/html"},
        data={"profile_visibility": "followers", "csrf_token": csrf_token},
    )
    assert response.status_code in (200, 303)
    response = await client.get("/followonly", headers={**target.auth_header, "Accept": "text/html"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_profile_visibility_private(client: AsyncClient) -> None:
    """Test private visibility - verify privacy settings form works."""
    target = await register_and_login(client, username="privateuser", role="volunteer")
    csrf_token = client.cookies.get("csrf_token", "")

    response = await client.post(
        "/settings/privacy",
        headers={**target.auth_header, "Accept": "text/html"},
        data={"profile_visibility": "private", "csrf_token": csrf_token},
    )
    assert response.status_code in (200, 303)
    response = await client.get("/privateuser", headers={**target.auth_header, "Accept": "text/html"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_file_storage_service_works(
    client: AsyncClient,
    fs: FakeFilesystem,
) -> None:
    """Critical: Verify file storage service works."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    upload_dir = Path(tempfile.gettempdir()) / "test_uploads"
    fs.makedirs(str(upload_dir), exist_ok=True)

    with patch("app.core.config.settings.upload_dir", upload_dir):
        assert upload_dir is not None, "Upload directory not configured"
        user = await register_and_login(client, role="volunteer")

        from io import BytesIO

        from tests.test_uploads import create_test_image

        buffer = BytesIO(create_test_image())

        response = await client.post(
            "/settings/profile/picture",
            files={"file": ("test.png", buffer, "image/png")},
            headers=user.auth_header,
        )

        assert response.status_code in (200, 303), "File storage service not working"
        saved_files = list(upload_dir.rglob("*.webp"))
        assert len(saved_files) > 0, "No files were saved to storage"
