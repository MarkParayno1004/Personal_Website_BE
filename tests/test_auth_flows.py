import re
import unittest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import AuditLog, Medication, User
from rate_limit import _hits
from security import create_access_token, create_purpose_token, hash_password


def _link_token(logs: list[str]) -> str:
    """Pull the token out of the link the dev mailer logs instead of sending."""
    match = re.search(r"token=([\w\-.]+)", "\n".join(logs))
    assert match, f"no link in logs: {logs}"
    return match.group(1)


class TestAuthFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
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
        db.add_all([
            User(id=1, email="admin@flows.com", first_name="A", last_name="D",
                 hashed_password=hash_password("adminpass1"), admin=True, email_verified=True),
            User(id=2, email="user@flows.com", first_name="U", last_name="S",
                 hashed_password=hash_password("userpass1")),
        ])
        db.commit()
        db.close()
        cls.admin_headers = {"Authorization": f"Bearer {create_access_token({'sub': '1'})}"}
        cls.user_headers = {"Authorization": f"Bearer {create_access_token({'sub': '2'})}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        _hits.clear()

    def test_register_sends_verification_link_and_confirm_verifies(self):
        payload = {"first_name": "V", "last_name": "E", "email": "verify@flows.com", "password": "verifypass1"}
        with self.assertLogs("mailer", "INFO") as logs:
            res = self.client.post("/auth/register", json=payload)
        self.assertEqual(res.status_code, 201)
        self.assertFalse(res.json()["email_verified"])

        token = _link_token(logs.output)
        confirm = self.client.post("/auth/verify-email/confirm", json={"token": token})
        self.assertEqual(confirm.status_code, 200)
        self.assertTrue(confirm.json()["email_verified"])

        self.assertEqual(self.client.post("/auth/verify-email/confirm", json={"token": "garbage"}).status_code, 400)

    def test_purpose_tokens_are_not_access_tokens(self):
        reset = create_purpose_token(2, "password_reset", timedelta(minutes=5), ver=0)
        self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {reset}"}).status_code, 401)
        # ...and an access token is not a verification token
        access = self.user_headers["Authorization"].split()[1]
        self.assertEqual(self.client.post("/auth/verify-email/confirm", json={"token": access}).status_code, 400)

    def test_password_reset_request_does_not_reveal_accounts(self):
        unknown = self.client.post("/auth/password-reset/request", json={"email": "nobody@flows.com"})
        known = self.client.post("/auth/password-reset/request", json={"email": "user@flows.com"})
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(known.status_code, 202)
        self.assertEqual(unknown.json(), known.json())

    def test_password_reset_flow_is_single_use_and_revokes_sessions(self):
        db = self.TestingSessionLocal()
        db.add(User(id=3, email="reset@flows.com", first_name="R", last_name="S", hashed_password=hash_password("oldpass123")))
        db.commit()
        db.close()
        old_session = {"Authorization": f"Bearer {create_access_token({'sub': '3', 'ver': 0})}"}

        with self.assertLogs("mailer", "INFO") as logs:
            self.client.post("/auth/password-reset/request", json={"email": "reset@flows.com"})
        token = _link_token(logs.output)

        weak = self.client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "short"})
        self.assertEqual(weak.status_code, 422)

        ok = self.client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "newpass123"})
        self.assertEqual(ok.status_code, 204)
        reused = self.client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "another123"})
        self.assertEqual(reused.status_code, 400)

        self.assertEqual(self.client.get("/auth/me", headers=old_session).status_code, 401)
        login = self.client.post("/auth/login", json={"email": "reset@flows.com", "password": "newpass123"})
        self.assertEqual(login.status_code, 200)

    def test_password_reset_request_is_rate_limited(self):
        for _ in range(5):
            self.client.post("/auth/password-reset/request", json={"email": "nobody@flows.com"})
        res = self.client.post("/auth/password-reset/request", json={"email": "nobody@flows.com"})
        self.assertEqual(res.status_code, 429)

    def test_audit_log_records_logins_without_secrets_and_is_admin_only(self):
        self.client.post("/auth/login", json={"email": "user@flows.com", "password": "wrong-password"})
        self.client.post("/auth/login", json={"email": "user@flows.com", "password": "userpass1"})

        self.assertEqual(self.client.get("/admin/audit-logs", headers=self.user_headers).status_code, 403)
        res = self.client.get("/admin/audit-logs", params={"action": "login_failed"}, headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        rows = res.json()
        self.assertTrue(rows)
        self.assertTrue(all(r["action"] == "login_failed" for r in rows))
        self.assertNotIn("wrong-password", res.text)
        self.assertEqual(int(res.headers["X-Total-Count"]), len(rows))

        db = self.TestingSessionLocal()
        self.assertTrue(db.query(AuditLog).filter(AuditLog.action == "login", AuditLog.actor_user_id == 2).count())
        db.close()

    def test_admin_role_change_is_audited(self):
        res = self.client.patch("/admin/users/2/role", json={"admin": False}, headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        logs = self.client.get("/admin/audit-logs", params={"action": "admin_role_change"}, headers=self.admin_headers).json()
        self.assertEqual(logs[0]["actor_user_id"], 1)
        self.assertEqual(logs[0]["target_id"], "2")

    def test_list_pagination_and_total_header(self):
        db = self.TestingSessionLocal()
        db.add_all([Medication(name=f"Med {i:02d}", cost=1.0, user_id=2) for i in range(5)])
        db.commit()
        db.close()

        res = self.client.get("/medications/", params={"limit": 2, "offset": 2}, headers=self.user_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["X-Total-Count"], "5")
        self.assertEqual([m["name"] for m in res.json()], ["Med 02", "Med 03"])

        self.assertEqual(self.client.get("/medications/", params={"limit": 101}, headers=self.user_headers).status_code, 422)
        self.assertEqual(self.client.get("/medications/", params={"offset": -1}, headers=self.user_headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()
