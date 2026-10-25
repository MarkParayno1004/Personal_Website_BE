import unittest
from fastapi.testclient import TestClient
from main import app
from security import decode_access_token


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
from models import User
from rate_limit import _hits
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
        cls.seed_token = create_access_token({"sub": "123", "email": "test@test.com"})
        cls.seed_user = User(
            id=123,
            email="test@test.com",
            first_name="test name",
            last_name="test last name",
            hashed_password=hash_password("123"),
            admin=False,
        )
        cls.admin_token = create_access_token({"sub": "900", "email": "admin@test.com"})
        cls.admin_user = User(
            id=900,
            email="admin@test.com",
            first_name="Admin",
            last_name="User",
            hashed_password=hash_password("adminpass123"),
            admin=True,
        )
        db.add_all([cls.seed_user, cls.admin_user])
        db.commit()
        db.close()

    def setUp(self):
        _hits.clear()  # rate-limit counters are process-global

    def _seed_user(self, user_id: int, email: str, password: str = "password123") -> dict:
        db = self.TestingSessionLocal()
        db.add(User(id=user_id, email=email, first_name="T", last_name="U", hashed_password=hash_password(password)))
        db.commit()
        db.close()
        return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id), 'email': email})}"}

    @classmethod
    def tearDownClass(cls):
        import shutil, os
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        root = os.path.dirname(os.path.dirname(__file__))
        for upload_dir in (os.path.join(root, "uploads", "profile_pictures"), os.path.join(root, "private_uploads", "documents")):
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir, ignore_errors=True)

    def test_get_user_does_not_contain_password_or_token(self):
        """Ensure GET /users/{user_id} needs auth and never returns password or token."""
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        response = self.client.get("/users/123", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("password", data)
        self.assertNotIn("hashed_password", data)
        self.assertNotIn("token", data)
        self.assertEqual(data["id"], 123)
        self.assertEqual(data["email"], "test@test.com")
        self.assertEqual(data["first_name"], "test name")

    def test_get_user_requires_auth_and_ownership(self):
        """Regression: GET /users/{id} used to be public and leak live JWTs."""
        self.assertEqual(self.client.get("/users/123").status_code, 401)
        # A normal user cannot read someone else
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        self.assertEqual(self.client.get("/users/900", headers=headers).status_code, 404)
        # An admin can
        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}
        self.assertEqual(self.client.get("/users/123", headers=admin_headers).status_code, 200)

    def test_admin_user_list_has_no_tokens(self):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        res = self.client.get("/admin/users", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(int(res.headers["X-Total-Count"]), 2)
        for user in res.json():
            self.assertNotIn("token", user)

    def test_register_rejects_weak_password(self):
        payload = {"first_name": "A", "last_name": "B", "email": "weak@example.com", "password": "short"}
        self.assertEqual(self.client.post("/auth/register", json=payload).status_code, 422)
        payload["password"] = "é" * 40  # 80 bytes, over bcrypt's 72-byte limit
        self.assertEqual(self.client.post("/auth/register", json=payload).status_code, 422)

    def test_login_with_overlong_password_is_401_not_500(self):
        res = self.client.post("/auth/login", json={"email": "test@test.com", "password": "x" * 200})
        self.assertEqual(res.status_code, 401)

    def test_login_rate_limited(self):
        for _ in range(10):
            self.client.post("/auth/login", json={"email": "test@test.com", "password": "wrong"})
        res = self.client.post("/login/", json={"email": "test@test.com", "password": "wrong"})
        self.assertEqual(res.status_code, 429)

    def test_logout_revokes_existing_tokens(self):
        headers = self._seed_user(301, "logout@example.com")
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)

    def test_change_password_flow(self):
        headers = self._seed_user(302, "changepw@example.com", "oldpassword1")
        bad = self.client.put(
            "/auth/me/password",
            json={"current_password": "wrong", "new_password": "newpassword1"},
            headers=headers,
        )
        self.assertEqual(bad.status_code, 400)

        res = self.client.put(
            "/auth/me/password",
            json={"current_password": "oldpassword1", "new_password": "newpassword1"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 200)
        # Old token revoked, new token works, new password logs in
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)
        new_headers = {"Authorization": f"Bearer {res.json()['token']}"}
        self.assertEqual(self.client.get("/auth/me", headers=new_headers).status_code, 200)
        login = self.client.post("/auth/login", json={"email": "changepw@example.com", "password": "newpassword1"})
        self.assertEqual(login.status_code, 200)

    def test_delete_account(self):
        headers = self._seed_user(303, "deleteme@example.com")
        self.assertEqual(self.client.delete("/auth/me", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)

    def test_last_admin_cannot_delete_account(self):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        self.assertEqual(self.client.delete("/auth/me", headers=headers).status_code, 400)

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["database"], "up")

    def test_security_headers_present(self):
        res = self.client.get("/")
        self.assertEqual(res.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(res.headers["X-Frame-Options"], "DENY")

    def test_github_rejects_path_tricks_in_username(self):
        res = self.client.get("/github/repos", params={"username": "../../user/repos"})
        self.assertEqual(res.status_code, 422)

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

    def test_protected_docs_access(self):
        """Ensure /docs is admin-only via Basic auth or Bearer token."""
        # Unauthenticated request should fail with 401
        unauth_res = self.client.get("/docs")
        self.assertEqual(unauth_res.status_code, 401)
        self.assertEqual(unauth_res.headers["WWW-Authenticate"], "Basic realm='Protected API Documentation'")

        # Non-admin credentials are refused
        self.assertEqual(self.client.get("/docs", auth=("test@test.com", "123")).status_code, 401)

        # HTTP Basic Auth using valid admin credentials
        auth_basic_res = self.client.get("/docs", auth=("admin@test.com", "adminpass123"))
        self.assertEqual(auth_basic_res.status_code, 200)

        # Bearer token for an admin
        token_res = self.client.get("/docs", headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(token_res.status_code, 200)

        # The ?token= query option was removed (it leaked JWTs into logs)
        self.assertEqual(self.client.get(f"/docs?token={self.admin_token}").status_code, 401)


    def test_upload_profile_picture_converts_to_webp_and_optimizes(self):
        """Ensure uploaded profile pictures are converted to WebP, resized, and saved."""
        import io
        from PIL import Image

        # Create a large test image (1000x800 RGB PNG)
        img_buffer = io.BytesIO()
        test_img = Image.new("RGB", (1000, 800), color="blue")
        test_img.save(img_buffer, format="PNG")
        img_bytes = img_buffer.getvalue()

        headers = {"Authorization": f"Bearer {self.seed_token}"}
        files = {"file": ("avatar.png", img_bytes, "image/png")}

        response = self.client.put("/auth/me/profile-picture", headers=headers, files=files)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data["profile_picture"])
        self.assertTrue(data["profile_picture"].endswith(".webp"))
        self.assertTrue(data["profile_picture"].startswith("/uploads/profile_pictures/"))

        # Verify the saved image dimensions on disk
        import os
        saved_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            data["profile_picture"].lstrip("/"),
        )
        self.assertTrue(os.path.exists(saved_path))
        with Image.open(saved_path) as saved_img:
            self.assertEqual(saved_img.format, "WEBP")
            self.assertLessEqual(saved_img.width, 512)
            self.assertLessEqual(saved_img.height, 512)

    def test_upload_profile_picture_invalid_extension(self):
        """Ensure unsupported file extensions are rejected with 400."""
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        files = {"file": ("script.sh", b"echo hello", "text/plain")}

        response = self.client.put("/auth/me/profile-picture", headers=headers, files=files)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not allowed", response.json()["detail"])

    def test_delete_profile_picture_flow(self):
        """Ensure profile picture can be deleted and file is removed."""
        import io
        from PIL import Image

        # First upload
        img_buffer = io.BytesIO()
        test_img = Image.new("RGB", (100, 100), color="red")
        test_img.save(img_buffer, format="JPEG")
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        files = {"file": ("test.jpg", img_buffer.getvalue(), "image/jpeg")}

        upload_res = self.client.put("/auth/me/profile-picture", headers=headers, files=files)
        self.assertEqual(upload_res.status_code, 200)
        pic_url = upload_res.json()["profile_picture"]

        # Now delete
        del_res = self.client.delete("/auth/me/profile-picture", headers=headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertIsNone(del_res.json()["profile_picture"])

        # Second delete should 404
        del_res2 = self.client.delete("/auth/me/profile-picture", headers=headers)
        self.assertEqual(del_res2.status_code, 404)

    def test_upload_user_cv_valid_pdf(self):
        """Test uploading a valid PDF CV by authenticated user."""
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        fake_pdf_content = b"%PDF-1.5\nFake user CV PDF body\n%%EOF"
        files = {"file": ("my_cv.pdf", fake_pdf_content, "application/pdf")}

        res = self.client.put("/auth/me/cv", headers=headers, files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # CVs are private: only presence is exposed, and only the owner can download it.
        self.assertTrue(data["has_cv"])
        self.assertNotIn("cv_url", data)
        download = self.client.get("/auth/me/cv", headers=headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, fake_pdf_content)
        self.assertEqual(download.headers["content-type"], "application/pdf")
        self.assertEqual(self.client.get("/auth/me/cv").status_code, 401)

    def test_upload_user_cv_rejects_non_pdf(self):
        """Test uploading non-PDF file returns 400."""
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        fake_content = b"Not a PDF"
        files = {"file": ("my_cv.docx", fake_content, "application/msword")}

        res = self.client.put("/auth/me/cv", headers=headers, files=files)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Only PDF files", res.json()["detail"])

    def test_delete_user_cv_flow(self):
        """Test deleting user CV."""
        headers = {"Authorization": f"Bearer {self.seed_token}"}
        fake_pdf_content = b"%PDF-1.4\ncontent\n%%EOF"
        files = {"file": ("cv.pdf", fake_pdf_content, "application/pdf")}

        self.client.put("/auth/me/cv", headers=headers, files=files)
        del_res = self.client.delete("/auth/me/cv", headers=headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(del_res.json()["has_cv"])
        self.assertEqual(self.client.get("/auth/me/cv", headers=headers).status_code, 404)

        # Second delete should return 404
        del_res2 = self.client.delete("/auth/me/cv", headers=headers)
        self.assertEqual(del_res2.status_code, 404)


if __name__ == "__main__":
    unittest.main()
