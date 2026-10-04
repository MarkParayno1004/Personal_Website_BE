import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import User
from security import create_access_token, hash_password


class TestIncomesModule(unittest.TestCase):
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
            id=501,
            email="income_user1@example.com",
            first_name="Income",
            last_name="User1",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        cls.user2 = User(
            id=502,
            email="income_user2@example.com",
            first_name="Income",
            last_name="User2",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        cls.admin_user = User(
            id=503,
            email="income_admin@example.com",
            first_name="Income",
            last_name="Admin",
            hashed_password=hash_password("password123"),
            admin=True,
        )
        db.add_all([cls.user1, cls.user2, cls.admin_user])
        db.commit()
        db.close()

        token1 = create_access_token({"sub": "501", "email": "income_user1@example.com"})
        cls.headers1 = {"Authorization": f"Bearer {token1}"}

        token2 = create_access_token({"sub": "502", "email": "income_user2@example.com"})
        cls.headers2 = {"Authorization": f"Bearer {token2}"}

        admin_token = create_access_token({"sub": "503", "email": "income_admin@example.com"})
        cls.admin_headers = {"Authorization": f"Bearer {admin_token}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_01_create_gross_income_with_tax_deductions(self):
        payload = {
            "title": "Primary Job - Software Engineer",
            "amount": 8000.0,
            "tax_deductions": [
                {"description": "Federal Tax", "amount": 1200.0},
                {"description": "State Tax", "amount": 400.0},
                {"description": "Health Insurance", "amount": 200.0},
            ],
        }
        res = self.client.post("/incomes/", json=payload, headers=self.headers1)
        self.assertEqual(res.status_code, 201)
        data = res.json()

        self.assertEqual(data["title"], "Primary Job - Software Engineer")
        self.assertEqual(data["amount"], 8000.0)
        self.assertEqual(data["total_tax_deductions"], 1800.0)
        self.assertEqual(data["net_income"], 6200.0)
        self.assertEqual(data["remaining_income"], 6200.0)
        self.assertEqual(len(data["tax_deductions"]), 3)
        self.assertEqual(len(data["expenses"]), 0)
        self.assertEqual(len(data["medications"]), 0)

    def test_02_get_all_gross_incomes(self):
        res = self.client.get("/incomes/", headers=self.headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data), 1)
        titles = [item["title"] for item in data]
        self.assertIn("Primary Job - Software Engineer", titles)

    def test_03_get_single_gross_income_by_id(self):
        create_res = self.client.post(
            "/incomes/",
            json={"title": "Freelance Work", "amount": 2500.0},
            headers=self.headers1,
        )
        income_id = create_res.json()["id"]

        res = self.client.get(f"/incomes/{income_id}", headers=self.headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], income_id)
        self.assertEqual(data["title"], "Freelance Work")
        self.assertEqual(data["amount"], 2500.0)
        self.assertEqual(data["net_income"], 2500.0)

    def test_04_update_gross_income(self):
        create_res = self.client.post(
            "/incomes/",
            json={"title": "Side Gig", "amount": 1000.0},
            headers=self.headers1,
        )
        income_id = create_res.json()["id"]

        res = self.client.patch(
            f"/incomes/{income_id}",
            json={"title": "Updated Side Gig", "amount": 1500.0},
            headers=self.headers1,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["title"], "Updated Side Gig")
        self.assertEqual(data["amount"], 1500.0)

    def test_05_add_and_remove_tax_deductions(self):
        create_res = self.client.post(
            "/incomes/",
            json={"title": "Consulting Income", "amount": 5000.0},
            headers=self.headers1,
        )
        income_id = create_res.json()["id"]

        # Add tax deduction
        add_res = self.client.post(
            f"/incomes/{income_id}/tax-deductions",
            json={"description": "Self-Employment Tax", "amount": 750.0},
            headers=self.headers1,
        )
        self.assertEqual(add_res.status_code, 200)
        data = add_res.json()
        self.assertEqual(data["total_tax_deductions"], 750.0)
        self.assertEqual(data["net_income"], 4250.0)
        deduction_id = data["tax_deductions"][0]["id"]

        # Delete tax deduction
        del_res = self.client.delete(
            f"/incomes/{income_id}/tax-deductions/{deduction_id}",
            headers=self.headers1,
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["total_tax_deductions"], 0.0)
        self.assertEqual(del_res.json()["net_income"], 5000.0)

    def test_06_create_expense_and_medication_linking_to_gross_income(self):
        inc_res = self.client.post(
            "/incomes/",
            json={"title": "Monthly Retainer", "amount": 4000.0},
            headers=self.headers1,
        )
        income_id = inc_res.json()["id"]

        # Create expense with gross_income_id (no need to supply gross_income)
        exp_res = self.client.post(
            "/expenses/",
            json={
                "title": "Cloud Hosting & Domains",
                "gross_income_id": income_id,
                "items": [{"description": "AWS Server", "amount": 250.0}],
            },
            headers=self.headers1,
        )
        self.assertEqual(exp_res.status_code, 201)
        self.assertEqual(exp_res.json()["gross_income_id"], income_id)

        # Create medication with gross_income_id
        med_res = self.client.post(
            "/medications/",
            json={
                "name": "Eye Drops",
                "cost": 25.0,
                "doses_taken": 2,
                "gross_income_id": income_id,
            },
            headers=self.headers1,
        )
        self.assertEqual(med_res.status_code, 201)
        self.assertEqual(med_res.json()["gross_income_id"], income_id)

        # Check GrossIncome response includes the linked expense and medication and computes remaining income
        inc_check = self.client.get(f"/incomes/{income_id}", headers=self.headers1)
        self.assertEqual(inc_check.status_code, 200)
        data = inc_check.json()
        self.assertEqual(len(data["expenses"]), 1)
        self.assertEqual(len(data["medications"]), 1)
        self.assertEqual(data["total_expenses"], 250.0)
        self.assertEqual(data["total_medications"], 50.0)
        # remaining_income = 4000 - 250 - 50 = 3700.0
        self.assertEqual(data["remaining_income"], 3700.0)

    def test_07_link_and_unlink_endpoints(self):
        inc_res = self.client.post(
            "/incomes/",
            json={"title": "Link Test Income", "amount": 3000.0},
            headers=self.headers1,
        )
        income_id = inc_res.json()["id"]

        # Standalone expense & med
        exp_res = self.client.post(
            "/expenses/",
            json={"title": "Office Supplies", "items": [{"description": "Notebooks", "amount": 30.0}]},
            headers=self.headers1,
        )
        exp_id = exp_res.json()["id"]

        med_res = self.client.post(
            "/medications/",
            json={"name": "Allergy Meds", "cost": 15.0, "doses_taken": 2},
            headers=self.headers1,
        )
        med_id = med_res.json()["id"]

        # Link to income via POST /incomes/{id}/link
        link_res = self.client.post(
            f"/incomes/{income_id}/link",
            json={"expense_ids": [exp_id], "medication_ids": [med_id]},
            headers=self.headers1,
        )
        self.assertEqual(link_res.status_code, 200)
        self.assertEqual(len(link_res.json()["expenses"]), 1)
        self.assertEqual(len(link_res.json()["medications"]), 1)

        # Unlink from income via POST /incomes/{id}/unlink
        unlink_res = self.client.post(
            f"/incomes/{income_id}/unlink",
            json={"expense_ids": [exp_id], "medication_ids": [med_id]},
            headers=self.headers1,
        )
        self.assertEqual(unlink_res.status_code, 200)
        self.assertEqual(len(unlink_res.json()["expenses"]), 0)
        self.assertEqual(len(unlink_res.json()["medications"]), 0)

        # Verify expense & med records still exist with gross_income_id=None
        exp_check = self.client.get(f"/expenses/{exp_id}", headers=self.headers1)
        self.assertIsNone(exp_check.json()["gross_income_id"])

        med_check = self.client.get(f"/medications/{med_id}", headers=self.headers1)
        self.assertIsNone(med_check.json()["gross_income_id"])

    def test_08_delete_gross_income_resets_child_links(self):
        inc_res = self.client.post(
            "/incomes/",
            json={"title": "To Delete Income", "amount": 2000.0},
            headers=self.headers1,
        )
        income_id = inc_res.json()["id"]

        exp_res = self.client.post(
            "/expenses/",
            json={"title": "Exp Attached", "gross_income_id": income_id, "items": []},
            headers=self.headers1,
        )
        exp_id = exp_res.json()["id"]

        del_res = self.client.delete(f"/incomes/{income_id}", headers=self.headers1)
        self.assertEqual(del_res.status_code, 204)

        # Expense still exists but gross_income_id is reset to None
        exp_check = self.client.get(f"/expenses/{exp_id}", headers=self.headers1)
        self.assertEqual(exp_check.status_code, 200)
        self.assertIsNone(exp_check.json()["gross_income_id"])

    def test_09_user_isolation(self):
        inc_res = self.client.post(
            "/incomes/",
            json={"title": "User 1 Secret Salary", "amount": 10000.0},
            headers=self.headers1,
        )
        income_id = inc_res.json()["id"]

        # User 2 cannot GET
        res = self.client.get(f"/incomes/{income_id}", headers=self.headers2)
        self.assertEqual(res.status_code, 404)

        # User 2 cannot PATCH
        res = self.client.patch(f"/incomes/{income_id}", json={"amount": 0.0}, headers=self.headers2)
        self.assertEqual(res.status_code, 404)

        # User 2 cannot link User 1's income to User 2's expense
        exp_res = self.client.post(
            "/expenses/",
            json={"title": "User 2 Exp", "gross_income_id": income_id, "items": []},
            headers=self.headers2,
        )
        self.assertEqual(exp_res.status_code, 404)

    def test_10_admin_stats_includes_gross_incomes(self):
        res = self.client.get("/admin/stats", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_gross_incomes", data)
        self.assertIn("total_gross_income_amount", data)
        self.assertGreater(data["total_gross_incomes"], 0)
        self.assertGreater(data["total_gross_income_amount"], 0.0)


if __name__ == "__main__":
    unittest.main()
