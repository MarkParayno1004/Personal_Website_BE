import unittest
from fastapi.testclient import TestClient
from main import app
from security import decode_access_token


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
from models import User
from security import create_access_token, hash_password


class TestMainApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=cls.engine
        )
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

        # Seed test user 123
        db = cls.TestingSessionLocal()
        seed_token = create_access_token({"sub": "123", "email": "test@test.com"})
        cls.seed_user = User(
            id=123,
            email="test@test.com",
            first_name="test name",
            last_name="test last name",
            hashed_password=hash_password("123"),
            token=seed_token,
            admin=False,
        )
        db.add(cls.seed_user)
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_get_user_does_not_contain_password(self):
        """Ensure GET /users/{user_id} does not return password."""
        response = self.client.get("/users/123")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("password", data)
        self.assertNotIn("hashed_password", data)
        self.assertEqual(data["id"], 123)
        self.assertEqual(data["email"], "test@test.com")
        self.assertEqual(data["first_name"], "test name")
        # Ensure the seed token is a valid JWT
        decoded = decode_access_token(data["token"])
        self.assertEqual(decoded["sub"], "123")

    def test_create_user_hashes_password_and_issues_jwt(self):
        """Ensure POST /users/ accepts password, issues JWT token, and hides password."""
        payload = {
            "first_name": "Bob",
            "last_name": "Marley",
            "email": "bob@example.com",
            "password": "supersecretpassword",
        }
        response = self.client.post("/users/", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertNotIn("password", data)
        self.assertNotIn("hashed_password", data)
        self.assertEqual(data["first_name"], "Bob")
        self.assertEqual(data["email"], "bob@example.com")

        # Verify issued JWT token
        token = data["token"]
        decoded = decode_access_token(token)
        self.assertEqual(decoded["email"], "bob@example.com")

    def test_login_flow(self):
        """Test login with valid and invalid credentials."""
        # Success login with seed user
        login_res = self.client.post(
            "/login/",
            json={"email": "test@test.com", "password": "123"},
        )
        self.assertEqual(login_res.status_code, 200)
        data = login_res.json()
        self.assertIn("token", data)
        self.assertNotIn("password", data)
        self.assertNotIn("hashed_password", data)

        # Invalid password
        fail_res = self.client.post(
            "/login/",
            json={"email": "test@test.com", "password": "wrongpassword"},
        )
        self.assertEqual(fail_res.status_code, 401)

    def test_openapi_schema_excludes_password_from_public_user(self):
        """Ensure password is not exposed in UserPublic OpenAPI schema."""
        openapi_schema = app.openapi()
        user_public_props = openapi_schema["components"]["schemas"]["UserPublic"]["properties"]
        self.assertNotIn("password", user_public_props)
        self.assertNotIn("hashed_password", user_public_props)


if __name__ == "__main__":
    unittest.main()
