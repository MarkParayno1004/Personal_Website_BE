import unittest
from fastapi.testclient import TestClient
from main import app
from database import Base, get_db
from models import User
from security import create_access_token, hash_password
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class TestPortfolioApi(unittest.TestCase):
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

        db = cls.TestingSessionLocal()
        cls.admin_token = create_access_token({"sub": "1", "email": "admin@test.com"})
        cls.admin_user = User(
            id=1,
            email="admin@test.com",
            first_name="Admin",
            last_name="User",
            hashed_password=hash_password("adminpass"),
            token=cls.admin_token,
            admin=True,
        )
        cls.non_admin_token = create_access_token({"sub": "2", "email": "user@test.com"})
        cls.normal_user = User(
            id=2,
            email="user@test.com",
            first_name="Normal",
            last_name="User",
            hashed_password=hash_password("userpass"),
            token=cls.non_admin_token,
            admin=False,
        )
        db.add(cls.admin_user)
        db.add(cls.normal_user)
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_get_portfolio_config_public(self):
        """Test public retrieval of portfolio configuration auto-populated from CV."""
        res = self.client.get("/portfolio/config")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["full_name"], "Mark Philip V. Parayno")
        self.assertIn("Software Engineer", data["headline"])
        self.assertEqual(data["email"], "paraynomarkphilip@gmail.com")
        self.assertIn("Languages", data["skills"])
        self.assertTrue(len(data["experience"]) >= 3)
        self.assertEqual(data["experience"][0]["company"], "Shopping Center Management Corporation (SM Prime Holdings, Inc.)")

    def test_update_portfolio_config_admin_success(self):
        """Test updating portfolio configuration with admin credentials."""
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        update_payload = {
            "headline": "Lead Full Stack & Mobile Engineer",
            "github_username": "MarkParayno1004",
        }
        res = self.client.put("/portfolio/config", json=update_payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["headline"], "Lead Full Stack & Mobile Engineer")

    def test_update_portfolio_config_non_admin_forbidden(self):
        """Test updating portfolio configuration with non-admin credentials fails with 403."""
        headers = {"Authorization": f"Bearer {self.non_admin_token}"}
        update_payload = {"headline": "Hacker Headline"}
        res = self.client.put("/portfolio/config", json=update_payload, headers=headers)
        self.assertEqual(res.status_code, 403)
