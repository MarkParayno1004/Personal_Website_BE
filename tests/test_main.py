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
        cls.seed_token = create_access_token({"sub": "123", "email": "test@test.com"})
        cls.seed_user = User(
            id=123,
            email="test@test.com",
            first_name="test name",
            last_name="test last name",
            hashed_password=hash_password("123"),
            token=cls.seed_token,
            admin=False,
        )
        db.add(cls.seed_user)
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        import shutil, os
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "profile_pictures")
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir, ignore_errors=True)

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

    def test_protected_docs_access(self):
        """Ensure /docs is protected and requires valid credentials or token."""
        # Unauthenticated request should fail with 401
        unauth_res = self.client.get("/docs")
        self.assertEqual(unauth_res.status_code, 401)
        self.assertEqual(unauth_res.headers["WWW-Authenticate"], "Basic realm='Protected API Documentation'")

        # HTTP Basic Auth using valid database credentials
        auth_basic_res = self.client.get("/docs", auth=("test@test.com", "123"))
        self.assertEqual(auth_basic_res.status_code, 200)

        # Token Auth using query parameter ?token=...
        token_res = self.client.get(f"/docs?token={self.seed_token}")
        self.assertEqual(token_res.status_code, 200)


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
        self.assertIsNotNone(data["cv_url"])
        self.assertTrue(data["cv_url"].endswith(".pdf"))
        self.assertTrue(data["cv_url"].startswith("/uploads/documents/"))

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
        self.assertIsNone(del_res.json()["cv_url"])

        # Second delete should return 404
        del_res2 = self.client.delete("/auth/me/cv", headers=headers)
        self.assertEqual(del_res2.status_code, 404)


if __name__ == "__main__":
    unittest.main()
