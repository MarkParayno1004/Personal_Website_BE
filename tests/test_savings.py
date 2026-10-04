import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Expense, User
from security import create_access_token, hash_password


class TestSavingsModule(unittest.TestCase):
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

        # Seed test users
        db = cls.TestingSessionLocal()
        cls.user1 = User(
            id=701,
            email="saving_user1@example.com",
            first_name="Saving",
            last_name="User1",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        cls.user2 = User(
            id=702,
            email="saving_user2@example.com",
            first_name="Saving",
            last_name="User2",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        cls.admin_user = User(
            id=703,
            email="saving_admin@example.com",
            first_name="Saving",
            last_name="Admin",
            hashed_password=hash_password("password123"),
            admin=True,
        )
        db.add_all([cls.user1, cls.user2, cls.admin_user])
        db.commit()

        # Seed an expense for user1
        cls.expense1 = Expense(
            id=701,
            title="Monthly Budget - May",
            gross_income=5000.0,
            net_income=4000.0,
            user_id=cls.user1.id,
        )
        db.add(cls.expense1)
        db.commit()
        db.close()

        token1 = create_access_token({"sub": "701", "email": "saving_user1@example.com"})
        cls.headers1 = {"Authorization": f"Bearer {token1}"}

        token2 = create_access_token({"sub": "702", "email": "saving_user2@example.com"})
        cls.headers2 = {"Authorization": f"Bearer {token2}"}

        admin_token = create_access_token({"sub": "703", "email": "saving_admin@example.com"})
        cls.admin_headers = {"Authorization": f"Bearer {admin_token}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_01_create_standalone_saving(self):
        """Create a saving without an expense_id (standalone saving)."""
        payload = {
            "title": "Emergency Fund",
            "items": [
                {"description": "Initial Deposit", "amount": 500.0},
                {"description": "March Transfer", "amount": 250.0},
            ],
        }
        res = self.client.post("/savings/", json=payload, headers=self.headers1)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Emergency Fund")
        self.assertIsNone(data["expense_id"])
        self.assertEqual(data["total_amount"], 750.0)
        self.assertEqual(len(data["items"]), 2)

    def test_02_create_saving_linked_to_expense(self):
        """Create a saving linked to an existing expense."""
        payload = {
            "title": "Vacation Travel Fund",
            "expense_id": 701,
            "items": [
                {"description": "Flight Savings", "amount": 300.0},
                {"description": "Hotel Savings", "amount": 200.0},
            ],
        }
        res = self.client.post("/savings/", json=payload, headers=self.headers1)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Vacation Travel Fund")
        self.assertEqual(data["expense_id"], 701)
        self.assertEqual(data["total_amount"], 500.0)

    def test_03_create_saving_invalid_expense_fails(self):
        """Creating a saving with a non-existent expense should return 404."""
        payload = {
            "title": "Invalid Saving",
            "expense_id": 99999,
            "items": [],
        }
        res = self.client.post("/savings/", json=payload, headers=self.headers1)
        self.assertEqual(res.status_code, 404)

    def test_04_get_savings_and_single_saving(self):
        """List user savings and fetch a single saving by ID."""
        list_res = self.client.get("/savings/", headers=self.headers1)
        self.assertEqual(list_res.status_code, 200)
        data = list_res.json()
        self.assertGreaterEqual(len(data), 2)

        saving_id = data[0]["id"]
        single_res = self.client.get(f"/savings/{saving_id}", headers=self.headers1)
        self.assertEqual(single_res.status_code, 200)
        self.assertEqual(single_res.json()["id"], saving_id)

    def test_05_update_saving(self):
        """Update saving title and replacement items."""
        create_res = self.client.post(
            "/savings/",
            json={"title": "Retirement", "items": [{"description": "401k", "amount": 1000.0}]},
            headers=self.headers1,
        )
        self.assertEqual(create_res.status_code, 201)
        saving_id = create_res.json()["id"]

        update_payload = {
            "title": "Retirement Portfolio",
            "items": [
                {"description": "401k Contribution", "amount": 1200.0},
                {"description": "Roth IRA", "amount": 500.0},
            ],
        }
        update_res = self.client.put(f"/savings/{saving_id}", json=update_payload, headers=self.headers1)
        self.assertEqual(update_res.status_code, 200)
        updated_data = update_res.json()
        self.assertEqual(updated_data["title"], "Retirement Portfolio")
        self.assertEqual(updated_data["total_amount"], 1700.0)
        self.assertEqual(len(updated_data["items"]), 2)

    def test_06_add_and_delete_saving_item(self):
        """Add an item to an existing saving and then delete it."""
        create_res = self.client.post(
            "/savings/",
            json={"title": "House Downpayment", "items": []},
            headers=self.headers1,
        )
        self.assertEqual(create_res.status_code, 201)
        saving_id = create_res.json()["id"]

        add_res = self.client.post(
            f"/savings/{saving_id}/items",
            json={"description": "First Installment", "amount": 2500.0},
            headers=self.headers1,
        )
        self.assertEqual(add_res.status_code, 200)
        add_data = add_res.json()
        self.assertEqual(add_data["total_amount"], 2500.0)
        self.assertEqual(len(add_data["items"]), 1)

        item_id = add_data["items"][0]["id"]
        del_res = self.client.delete(f"/savings/{saving_id}/items/{item_id}", headers=self.headers1)
        self.assertEqual(del_res.status_code, 200)
        del_data = del_res.json()
        self.assertEqual(del_data["total_amount"], 0.0)
        self.assertEqual(len(del_data["items"]), 0)

    def test_07_link_and_unlink_expense(self):
        """Link a standalone saving to an expense, then unlink it."""
        create_res = self.client.post(
            "/savings/",
            json={"title": "Gadget Upgrade", "items": [{"description": "Laptop fund", "amount": 800.0}]},
            headers=self.headers1,
        )
        self.assertEqual(create_res.status_code, 201)
        saving_id = create_res.json()["id"]

        link_res = self.client.post(
            f"/savings/{saving_id}/link",
            json={"expense_id": 701},
            headers=self.headers1,
        )
        self.assertEqual(link_res.status_code, 200)
        self.assertEqual(link_res.json()["expense_id"], 701)

        unlink_res = self.client.post(
            f"/savings/{saving_id}/unlink",
            headers=self.headers1,
        )
        self.assertEqual(unlink_res.status_code, 200)
        self.assertIsNone(unlink_res.json()["expense_id"])

    def test_08_delete_saving(self):
        """Delete a saving record."""
        create_res = self.client.post(
            "/savings/",
            json={"title": "To be deleted", "items": []},
            headers=self.headers1,
        )
        saving_id = create_res.json()["id"]

        del_res = self.client.delete(f"/savings/{saving_id}", headers=self.headers1)
        self.assertEqual(del_res.status_code, 204)

        get_res = self.client.get(f"/savings/{saving_id}", headers=self.headers1)
        self.assertEqual(get_res.status_code, 404)

    def test_09_user_isolation(self):
        """User 2 cannot access or modify User 1's savings."""
        create_res = self.client.post(
            "/savings/",
            json={"title": "User 1 Secret Fund", "items": [{"description": "Cash", "amount": 100.0}]},
            headers=self.headers1,
        )
        saving_id = create_res.json()["id"]

        # User 2 tries to get
        res_get = self.client.get(f"/savings/{saving_id}", headers=self.headers2)
        self.assertEqual(res_get.status_code, 404)

        # User 2 tries to delete
        res_del = self.client.delete(f"/savings/{saving_id}", headers=self.headers2)
        self.assertEqual(res_del.status_code, 404)

    def test_10_expense_response_includes_attached_savings(self):
        """Expense endpoint returns attached savings in its payload."""
        # Check expense 701
        exp_res = self.client.get("/expenses/701", headers=self.headers1)
        self.assertEqual(exp_res.status_code, 200)
        exp_data = exp_res.json()
        self.assertIn("savings", exp_data)
        self.assertIn("total_savings", exp_data)

    def test_11_admin_stats_includes_savings(self):
        """Admin stats endpoint aggregates savings count and amount."""
        admin_res = self.client.get("/admin/stats", headers=self.admin_headers)
        self.assertEqual(admin_res.status_code, 200)
        data = admin_res.json()
        self.assertIn("total_savings", data)
        self.assertIn("total_savings_amount", data)
        self.assertGreater(data["total_savings"], 0)
        self.assertGreater(data["total_savings_amount"], 0.0)


if __name__ == "__main__":
    unittest.main()
