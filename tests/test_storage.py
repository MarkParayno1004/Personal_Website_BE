import os
import shutil
import tempfile
import unittest
from unittest import mock

import storage


class TestLocalStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = mock.patch.multiple(
            storage,
            USE_R2=False,
            PUBLIC_DIR=os.path.join(self.tmp, "public"),
            PRIVATE_DIR=os.path.join(self.tmp, "private"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_public_roundtrip(self):
        url = storage.put_public("profile_pictures/a.webp", b"img", "image/webp")
        self.assertEqual(url, "/uploads/profile_pictures/a.webp")
        path = os.path.join(self.tmp, "public", "profile_pictures", "a.webp")
        self.assertTrue(os.path.exists(path))
        storage.delete_public(url)
        self.assertFalse(os.path.exists(path))

    def test_private_roundtrip_is_outside_public_dir(self):
        key = storage.put_private("documents/cv.pdf", b"%PDF-1.4", "application/pdf")
        self.assertEqual(storage.get_private(key), b"%PDF-1.4")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "public", "documents", "cv.pdf")))
        storage.delete_private(key)
        self.assertIsNone(storage.get_private(key))

    def test_keys_cannot_escape_storage_root(self):
        with self.assertRaises(ValueError):
            storage.put_private("../escape.pdf", b"x", "application/pdf")
        self.assertIsNone(storage.get_private("../../etc/passwd"))
        # Legacy or foreign URLs are ignored, never resolved to arbitrary paths
        storage.delete_public("https://elsewhere.example/x.webp")


class TestR2Storage(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        patcher = mock.patch.multiple(
            storage,
            USE_R2=True,
            R2_BUCKET="public-bucket",
            R2_PRIVATE_BUCKET="private-bucket",
            R2_PUBLIC_BASE_URL="https://cdn.example.com",
            _client=self.client,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_public_put_and_delete_use_public_bucket(self):
        url = storage.put_public("profile_pictures/a.webp", b"img", "image/webp")
        self.assertEqual(url, "https://cdn.example.com/profile_pictures/a.webp")
        self.client.put_object.assert_called_once_with(
            Bucket="public-bucket", Key="profile_pictures/a.webp", Body=b"img", ContentType="image/webp"
        )
        storage.delete_public(url)
        self.client.delete_object.assert_called_once_with(Bucket="public-bucket", Key="profile_pictures/a.webp")

    def test_private_files_use_private_bucket(self):
        storage.put_private("documents/cv.pdf", b"%PDF", "application/pdf")
        self.assertEqual(self.client.put_object.call_args.kwargs["Bucket"], "private-bucket")
        self.client.get_object.return_value = {"Body": mock.Mock(read=lambda: b"%PDF")}
        self.assertEqual(storage.get_private("documents/cv.pdf"), b"%PDF")

    def test_missing_private_object_returns_none(self):
        err = Exception("missing")
        err.response = {"Error": {"Code": "NoSuchKey"}}
        self.client.get_object.side_effect = err
        self.assertIsNone(storage.get_private("documents/gone.pdf"))


if __name__ == "__main__":
    unittest.main()
