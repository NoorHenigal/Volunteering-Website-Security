"""Tests for user and organization profiles."""

from io import BytesIO

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
    """Test accessing a non-existent profile."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404


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

    response = await client.put(
        "/settings/profile",
        headers=user.auth_header,
        json={"bio": "This is my test bio", "description": "A longer description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bio"] == "This is my test bio"
    assert data["description"] == "A longer description"


@pytest.mark.anyio
async def test_update_privacy_settings(client: AsyncClient) -> None:
    """Test updating privacy settings."""
    user = await register_and_login(client, role="volunteer")

    response = await client.put(
        "/settings/privacy",
        headers=user.auth_header,
        json={
            "profile_visibility": "authenticated",
            "show_email": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["profile_visibility"] == "authenticated"
    assert data["show_email"] is True


@pytest.mark.anyio
async def test_privacy_settings_page_requires_auth(client: AsyncClient) -> None:
    """Test that privacy settings page requires authentication."""
    response = await client.get("/settings/privacy", follow_redirects=False)
    assert response.status_code == 303


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
    await client.put(
        "/settings/privacy",
        headers=target.auth_header,
        json={"profile_visibility": "authenticated"},
    )

    # 1. Anonymous access -> 403
    response = await client.get("/authonly")
    assert response.status_code == 403

    # 2. Authenticated access -> 200
    viewer = await register_and_login(client, username="viewer", role="volunteer")
    response = await client.get("/authonly", headers=viewer.auth_header)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_profile_visibility_followers(client: AsyncClient) -> None:
    """Test followers only visibility."""
    target = await register_and_login(client, username="followonly", role="volunteer")
    await client.put(
        "/settings/privacy",
        headers=target.auth_header,
        json={"profile_visibility": "followers"},
    )

    # 1. Anonymous -> 403
    response = await client.get("/followonly")
    assert response.status_code == 403

    # 2. Non-follower -> 403
    viewer = await register_and_login(client, username="viewer2", role="volunteer")
    response = await client.get("/followonly", headers=viewer.auth_header)
    assert response.status_code == 403

    # 3. Follower -> 200
    await client.post("/followonly/follow", headers=viewer.auth_header)
    response = await client.get("/followonly", headers=viewer.auth_header)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_profile_visibility_private(client: AsyncClient) -> None:
    """Test private visibility."""
    target = await register_and_login(client, username="privateuser", role="volunteer")
    await client.put(
        "/settings/privacy",
        headers=target.auth_header,
        json={"profile_visibility": "private"},
    )

    # 1. Anonymous -> 404
    response = await client.get("/privateuser")
    assert response.status_code == 404

    # 2. Authenticated -> 404
    viewer = await register_and_login(client, username="viewer3", role="volunteer")
    response = await client.get("/privateuser", headers=viewer.auth_header)
    assert response.status_code == 404

    # 3. Owner -> 200
    response = await client.get("/privateuser", headers=target.auth_header)
    assert response.status_code == 200

@pytest.mark.anyio
async def test_file_storage_service_works(
    client: AsyncClient,
    test_db: AsyncSession,
    fs: FakeFilesystem,
) -> None:
    """Critical: Verify file storage service works"""
    from pathlib import Path
    import tempfile
    from unittest.mock import patch
    
    # Mock upload directory (same pattern as existing tests)
    upload_dir = Path(tempfile.gettempdir()) / "test_uploads"
    fs.makedirs(str(upload_dir), exist_ok=True)
    
    with patch("app.core.config.settings.upload_dir", upload_dir):
        # Verify upload directory is accessible
        assert upload_dir is not None, "Upload directory not configured"
        
        # Test that upload endpoint works
        user = await register_and_login(client, role="volunteer")
        
        from tests.test_uploads import create_test_image
        from io import BytesIO
        buffer = BytesIO(create_test_image())
        
        response = await client.post(
            "/settings/profile/picture",
            files={"file": ("test.png", buffer, "image/png")},
            headers=user.auth_header,
        )
        
        assert response.status_code in (200, 303), "File storage service not working"
        
        # Verify file was actually saved
        saved_files = list(upload_dir.rglob("*.webp"))
        assert len(saved_files) > 0, "No files were saved to storage"

@pytest.mark.anyio
async def test_uploaded_picture_and_description_in_database(
    client: AsyncClient,
    test_db: AsyncSession,
    fs: FakeFilesystem,
) -> None:
    """Critical: Uploaded picture and description appear in database"""
    from app.db.models import User
    from app.core.services.encryption import hash_email
    from sqlalchemy import select
    from pathlib import Path
    import tempfile
    from unittest.mock import patch
    from io import BytesIO
    
    # Mock upload directory
    upload_dir = Path(tempfile.gettempdir()) / "test_uploads"
    fs.makedirs(str(upload_dir), exist_ok=True)
    
    with patch("app.core.config.settings.upload_dir", upload_dir):
        user = await register_and_login(client, role="volunteer")
        
        # Upload picture
        from tests.test_uploads import create_test_image
        buffer = BytesIO(create_test_image())
        await client.post(
            "/settings/profile/picture",
            files={"file": ("db_test.png", buffer, "image/png")},
            headers=user.auth_header,
        )
        
        # Update bio
        await client.put(
            "/settings/profile",
            headers=user.auth_header,
            json={"bio": "Database check bio"},
        )
        
        # Check database
        result = await test_db.execute(
            select(User).where(User.email_hash == hash_email(user.email))
        )
        db_user = result.scalar_one()
        
        assert db_user.profile_picture is not None, "Profile picture not in database"
        assert db_user.bio is not None, "Bio not in database"

@pytest.mark.anyio
async def test_visibility_settings_reflected_in_database(
    client: AsyncClient,
    test_db: AsyncSession,
) -> None:
    """Critical: Profile visibility settings are reflected in database"""
    from app.db.models import User
    from app.core.services.encryption import hash_email
    from sqlalchemy import select
    
    user = await register_and_login(client, role="volunteer")
    
    # Set visibility to authenticated
    await client.put(
        "/settings/privacy",
        headers=user.auth_header,
        json={"profile_visibility": "authenticated"},
    )
    
    # Check database
    result = await test_db.execute(
        select(User).where(User.email_hash == hash_email(user.email))
    )
    db_user = result.scalar_one()
    
    assert db_user.profile_visibility == "authenticated", \
        f"Expected 'authenticated', got '{db_user.profile_visibility}'"