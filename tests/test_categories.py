import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import Category, Expense, Medication, User
from security import create_access_token, hash_password


class TestCategoriesModule(unittest.TestCase):
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
            id=101,
            email="cat_user1@example.com",
            first_name="Category",
            last_name="User1",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        cls.user2 = User(
            id=102,
            email="cat_user2@example.com",
            first_name="Category",
            last_name="User2",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        db.add_all([cls.user1, cls.user2])
        db.commit()
        db.close()

        token1 = create_access_token({"sub": "101", "email": "cat_user1@example.com"})
        cls.headers1 = {"Authorization": f"Bearer {token1}"}

        token2 = create_access_token({"sub": "102", "email": "cat_user2@example.com"})
        cls.headers2 = {"Authorization": f"Bearer {token2}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_01_create_empty_category(self):
        payload = {"title": "Health & Wellness"}
        res = self.client.post("/categories/", json=payload, headers=self.headers1)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Health & Wellness")
        self.assertEqual(data["user_id"], 101)
        self.assertEqual(len(data["expenses"]), 0)
        self.assertEqual(len(data["medications"]), 0)
        self.assertEqual(data["total_amount"], 0.0)

    def test_02_create_category_with_inline_expenses_and_medications(self):
        payload = {
            "title": "Medical & Prescriptions",
            "expenses": [
                {
                    "title": "Doctor Consultations",
                    "gross_income": 1000.0,
                    "items": [{"description": "General Checkup", "amount": 150.0}],
                    "tax_deductions": [{"description": "Medical Expense Deduction", "amount": 50.0}],
                }
            ],
            "medications": [
                {
                    "name": "Vitamin D",
                    "cost": 15.0,
                    "doses_taken": 4,
                }
            ],
        }
        res = self.client.post("/categories/", json=payload, headers=self.headers1)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Medical & Prescriptions")
        self.assertEqual(len(data["expenses"]), 1)
        self.assertEqual(len(data["medications"]), 1)
        self.assertEqual(data["expenses"][0]["title"], "Doctor Consultations")
        self.assertEqual(data["expenses"][0]["total_expenses"], 150.0)
        self.assertEqual(data["medications"][0]["name"], "Vitamin D")
        self.assertEqual(data["medications"][0]["total_spent"], 60.0)
        self.assertEqual(data["total_expenses_amount"], 150.0)
        self.assertEqual(data["total_medications_amount"], 60.0)
        self.assertEqual(data["total_amount"], 210.0)

    def test_03_get_all_categories(self):
        res = self.client.get("/categories/", headers=self.headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data), 2)
        titles = [c["title"] for c in data]
        self.assertIn("Health & Wellness", titles)
        self.assertIn("Medical & Prescriptions", titles)

    def test_04_get_single_category(self):
        # Create category
        create_res = self.client.post(
            "/categories/",
            json={"title": "Single Cat Test"},
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]

        res = self.client.get(f"/categories/{cat_id}", headers=self.headers1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], cat_id)
        self.assertEqual(data["title"], "Single Cat Test")

    def test_05_update_category(self):
        create_res = self.client.post(
            "/categories/",
            json={"title": "Original Title"},
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]

        res = self.client.patch(
            f"/categories/{cat_id}",
            json={"title": "Updated Title"},
            headers=self.headers1,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["title"], "Updated Title")

    def test_06_create_expense_inside_category_nested_mutation(self):
        create_res = self.client.post(
            "/categories/",
            json={"title": "Household Expenses"},
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]

        expense_payload = {
            "title": "Utilities March",
            "gross_income": 3000.0,
            "items": [
                {"description": "Electricity", "amount": 120.0},
                {"description": "Water", "amount": 40.0},
            ],
            "tax_deductions": [],
        }
        res = self.client.post(
            f"/categories/{cat_id}/expenses",
            json=expense_payload,
            headers=self.headers1,
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Utilities March")
        self.assertEqual(data["category_id"], cat_id)
        self.assertEqual(data["total_expenses"], 160.0)

        # Check that category now contains this expense
        cat_res = self.client.get(f"/categories/{cat_id}", headers=self.headers1)
        self.assertEqual(len(cat_res.json()["expenses"]), 1)
        self.assertEqual(cat_res.json()["total_expenses_amount"], 160.0)

    def test_07_create_medication_inside_category_nested_mutation(self):
        create_res = self.client.post(
            "/categories/",
            json={"title": "Daily Prescriptions"},
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]

        med_payload = {
            "name": "Amoxicillin",
            "cost": 12.5,
            "doses_taken": 2,
        }
        res = self.client.post(
            f"/categories/{cat_id}/medications",
            json=med_payload,
            headers=self.headers1,
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["name"], "Amoxicillin")
        self.assertEqual(data["category_id"], cat_id)
        self.assertEqual(data["total_spent"], 25.0)

        # Check that category now contains this medication
        cat_res = self.client.get(f"/categories/{cat_id}", headers=self.headers1)
        self.assertEqual(len(cat_res.json()["medications"]), 1)
        self.assertEqual(cat_res.json()["total_medications_amount"], 25.0)

    def test_08_create_expense_and_medication_with_category_id_standalone_routes(self):
        create_res = self.client.post(
            "/categories/",
            json={"title": "Travel & Meds"},
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]

        # Standalone expense creation referencing category_id
        exp_res = self.client.post(
            "/expenses/",
            json={
                "title": "Flight Tickets",
                "gross_income": 0.0,
                "category_id": cat_id,
                "items": [{"description": "Airline ticket", "amount": 450.0}],
            },
            headers=self.headers1,
        )
        self.assertEqual(exp_res.status_code, 201)
        self.assertEqual(exp_res.json()["category_id"], cat_id)

        # Standalone medication creation referencing category_id
        med_res = self.client.post(
            "/medications/",
            json={
                "name": "Motion Sickness Pills",
                "cost": 5.0,
                "doses_taken": 3,
                "category_id": cat_id,
            },
            headers=self.headers1,
        )
        self.assertEqual(med_res.status_code, 201)
        self.assertEqual(med_res.json()["category_id"], cat_id)

        # Category check
        cat_res = self.client.get(f"/categories/{cat_id}", headers=self.headers1)
        self.assertEqual(len(cat_res.json()["expenses"]), 1)
        self.assertEqual(len(cat_res.json()["medications"]), 1)
        self.assertEqual(cat_res.json()["total_amount"], 465.0)

    def test_09_cascade_delete_category(self):
        create_res = self.client.post(
            "/categories/",
            json={
                "title": "To Be Deleted",
                "expenses": [
                    {
                        "title": "Temp Expense",
                        "items": [{"description": "Temp item", "amount": 50.0}],
                    }
                ],
                "medications": [
                    {
                        "name": "Temp Med",
                        "cost": 10.0,
                        "doses_taken": 1,
                    }
                ],
            },
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]
        exp_id = create_res.json()["expenses"][0]["id"]
        med_id = create_res.json()["medications"][0]["id"]

        del_res = self.client.delete(f"/categories/{cat_id}", headers=self.headers1)
        self.assertEqual(del_res.status_code, 204)

        # Confirm category is gone
        get_cat_res = self.client.get(f"/categories/{cat_id}", headers=self.headers1)
        self.assertEqual(get_cat_res.status_code, 404)

        # Confirm cascaded expense is gone
        get_exp_res = self.client.get(f"/expenses/{exp_id}", headers=self.headers1)
        self.assertEqual(get_exp_res.status_code, 404)

        # Confirm cascaded medication is gone
        get_med_res = self.client.get(f"/medications/{med_id}", headers=self.headers1)
        self.assertEqual(get_med_res.status_code, 404)

    def test_10_user_isolation(self):
        create_res = self.client.post(
            "/categories/",
            json={"title": "User 1 Private Category"},
            headers=self.headers1,
        )
        cat_id = create_res.json()["id"]

        # User 2 tries to GET
        res = self.client.get(f"/categories/{cat_id}", headers=self.headers2)
        self.assertEqual(res.status_code, 404)

        # User 2 tries to PATCH
        res = self.client.patch(
            f"/categories/{cat_id}",
            json={"title": "Hacked Title"},
            headers=self.headers2,
        )
        self.assertEqual(res.status_code, 404)

        # User 2 tries to create expense inside User 1's category
        res = self.client.post(
            f"/categories/{cat_id}/expenses",
            json={"title": "Hacked Expense", "items": []},
            headers=self.headers2,
        )
        self.assertEqual(res.status_code, 404)

        # User 2 tries to DELETE
        res = self.client.delete(f"/categories/{cat_id}", headers=self.headers2)
        self.assertEqual(res.status_code, 404)

    def test_11_invalid_category_id_on_expenses_or_medications_returns_404(self):
        res = self.client.post(
            "/expenses/",
            json={"title": "Invalid Cat Exp", "category_id": 99999},
            headers=self.headers1,
        )
        self.assertEqual(res.status_code, 404)

        res = self.client.post(
            "/medications/",
            json={"name": "Invalid Cat Med", "cost": 10.0, "category_id": 99999},
            headers=self.headers1,
        )
        self.assertEqual(res.status_code, 404)
