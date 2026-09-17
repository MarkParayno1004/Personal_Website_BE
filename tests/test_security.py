import unittest
import jwt
from security import (
    HEADER,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestSecurity(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        password = "my_secure_password"
        hashed = hash_password(password)

        # Ensure hash is bcrypt format and not plaintext
        self.assertNotEqual(password, hashed)
        self.assertTrue(hashed.startswith("$2b$"))

        # Verify correct and incorrect passwords
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_jwt_token_generation_and_decoding(self):
        data = {"sub": "123", "email": "test@example.com"}
        token = create_access_token(data)

        # Token should be a non-empty string with standard 3 JWT parts
        self.assertIsInstance(token, str)
        self.assertEqual(len(token.split(".")), 3)

        # Verify custom header is included in the token
        unverified_header = jwt.get_unverified_header(token)
        self.assertEqual(unverified_header.get("alg"), HEADER["alg"])
        self.assertEqual(unverified_header.get("type"), HEADER["type"])

        decoded = decode_access_token(token)
        self.assertEqual(decoded["sub"], "123")
        self.assertEqual(decoded["email"], "test@example.com")
        self.assertIn("exp", decoded)

    def test_invalid_jwt_token_fails(self):
        with self.assertRaises(jwt.PyJWTError):
            decode_access_token("invalid.token.payload")


if __name__ == "__main__":
    unittest.main()
