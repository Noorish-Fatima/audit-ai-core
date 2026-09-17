"""Auth system pytest tests"""
import pytest
from fastapi.testclient import TestClient


def get_app():
    from app.main import app
    return TestClient(app)


class TestRegister:
    def test_register_successful(self):
        """Test that a new user can register successfully"""
        client = get_app()
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "testuser@example.com", "password": "password123", "role": "auditor"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "testuser@example.com"
        assert data["user"]["role"] == "auditor"
        assert "access_token" in data
        assert data["token_type"] == "bearer"


class TestLogin:
    def test_login_successful(self):
        """Test that a user can login with correct credentials"""
        client = get_app()
        # First register
        client.post("/api/v1/auth/register", json={
            "email": "loginuser@example.com",
            "password": "password123",
            "role": "auditor"
        })
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "loginuser@example.com", "password": "password123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "loginuser@example.com"
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self):
        """Test that login fails with generic error on wrong password"""
        client = get_app()
        # First register
        client.post("/api/v1/auth/register", json={
            "email": "badpass@example.com",
            "password": "password123",
            "role": "auditor"
        })
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "badpass@example.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self):
        """Test that login fails for nonexistent user"""
        client = get_app()
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "password123"}
        )
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]


class TestRefresh:
    def test_refresh_token(self):
        """Test that refresh token works and rotates the token"""
        client = get_app()
        # Register
        client.post("/api/v1/auth/register", json={
            "email": "refreshtest@example.com",
            "password": "password123",
            "role": "auditor"
        })
        
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "refreshtest@example.com", "password": "password123"}
        )
        assert login_resp.status_code == 200
        
        # Extract refresh token from cookie
        refresh_token = login_resp.cookies.get("refresh_token")
        assert refresh_token is not None
        
        # Use refresh token
        response = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        
        # Old refresh token should be revoked, new one issued
        new_refresh_token = response.cookies.get("refresh_token")
        assert new_refresh_token is not None
        assert new_refresh_token != refresh_token

    def test_refresh_token_no_cookie(self):
        """Test that refresh fails without cookie"""
        client = get_app()
        
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    def test_refresh_token_invalid(self):
        """Test that refresh fails with invalid token"""
        client = get_app()
        
        response = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": "invalidtoken123"}
        )
        assert response.status_code == 401


class TestLogout:
    def test_logout(self):
        """Test that logout revokes refresh token and clears cookie"""
        client = get_app()
        # Register
        client.post("/api/v1/auth/register", json={
            "email": "logouttest@example.com",
            "password": "password123",
            "role": "auditor"
        })
        
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "logouttest@example.com", "password": "password123"}
        )
        assert login_resp.status_code == 200
        
        refresh_token = login_resp.cookies.get("refresh_token")
        assert refresh_token is not None
        
        # Logout
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        
        # Cookie should be deleted
        assert response.cookies.get("refresh_token") == ""

    def test_logout_no_token(self):
        """Test that logout works even without refresh token"""
        client = get_app()
        
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200


class TestMe:
    def test_me_with_valid_token(self):
        """Test that me endpoint works with valid access token"""
        client = get_app()
        # Register
        client.post("/api/v1/auth/register", json={
            "email": "metest@example.com",
            "password": "password123",
            "role": "auditor"
        })
        
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "metest@example.com", "password": "password123"}
        )
        assert login_resp.status_code == 200
        
        access_token = login_resp.json()["access_token"]
        
        # Get user info
        response = client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "metest@example.com"
        assert data["role"] == "auditor"

    def test_me_without_token(self):
        """Test that me endpoint fails without token"""
        client = get_app()
        
        response = client.get("/api/v1/auth/me/")
        assert response.status_code == 401

    def test_me_invalid_token(self):
        """Test that me endpoint fails with invalid token"""
        client = get_app()
        
        response = client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": "Bearer invalidtoken"}
        )
        assert response.status_code == 401


class TestRoleBasedAccess:
    def test_me_as_approver_can_access(self):
        """Test that approver role can access me endpoint"""
        client = get_app()
        
        client.post("/api/v1/auth/register", json={
            "email": "approvertest@example.com",
            "password": "password123",
            "role": "approver"
        })
        
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "approvertest@example.com", "password": "password123"}
        )
        assert login_resp.status_code == 200
        
        access_token = login_resp.json()["access_token"]
        response = client.get(
            "/api/v1/auth/me/",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        assert response.status_code == 200

    def test_multiple_users_different_roles(self):
        """Test that different roles work correctly"""
        client = get_app()
        
        # Create admin
        client.post("/api/v1/auth/register", json={
            "email": "admintest@example.com",
            "password": "password123",
            "role": "admin"
        })
        
        # Create approver
        client.post("/api/v1/auth/register", json={
            "email": "approvertest2@example.com",
            "password": "password123",
            "role": "approver"
        })
        
        # Login as admin
        admin_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admintest@example.com", "password": "password123"}
        )
        admin_token = admin_resp.json()["access_token"]
        
        # Login as approver
        approver_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "approvertest2@example.com", "password": "password123"}
        )
        approver_token = approver_resp.json()["access_token"]
        
        # Both should be able to access me
        admin_me = client.get("/api/v1/auth/me/", headers={"Authorization": f"Bearer {admin_token}"})
        approver_me = client.get("/api/v1/auth/me/", headers={"Authorization": f"Bearer {approver_token}"})
        
        assert admin_me.status_code == 200
        assert approver_me.status_code == 200