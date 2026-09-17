import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import User
from security import create_access_token, hash_password


class TestExpensesModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Setup in-memory SQLite database for test isolation
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

        # Seed test user
        db = cls.TestingSessionLocal()
        cls.test_user = User(
            id=999,
            email="expense_tester@example.com",
            first_name="Expense",
            last_name="Tester",
            hashed_password=hash_password("password123"),
            admin=False,
        )
        db.add(cls.test_user)
        db.commit()
        db.close()

        # Token for authenticated requests
        token = create_access_token({"sub": "999", "email": "expense_tester@example.com"})
        cls.headers = {"Authorization": f"Bearer {token}"}

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_create_expense_with_gross_net_and_deductions(self):
        """Test creating an expense sheet with gross income, net income, multiple expenses, and tax deductions."""
        payload = {
            "title": "Monthly Budget - April",
            "gross_income": 7000.0,
            "net_income": 5200.0,
            "items": [
                {"description": "Apartment Rent", "amount": 1800.0},
                {"description": "Utilities", "amount": 250.0},
                {"description": "Groceries", "amount": 600.0},
            ],
            "tax_deductions": [
                {"description": "Federal Income Tax", "amount": 1100.0},
                {"description": "State Income Tax", "amount": 400.0},
                {"description": "Social Security & Medicare", "amount": 300.0},
            ],
        }
        res = self.client.post("/expenses/", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 201)
        data = res.json()

        self.assertEqual(data["title"], "Monthly Budget - April")
        self.assertEqual(data["gross_income"], 7000.0)
        self.assertEqual(data["net_income"], 5200.0)
        self.assertEqual(data["total_tax_deductions"], 1800.0)
        self.assertEqual(data["total_expenses"], 2650.0)
        self.assertEqual(data["total_amount"], 2650.0)
        # remaining_income = net_income (5200) - total_expenses (2650) = 2550
        self.assertEqual(data["remaining_income"], 2550.0)
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(len(data["tax_deductions"]), 3)

    def test_create_expense_auto_computes_net_income_when_omitted(self):
        """When net_income is omitted, it should auto-calculate: gross_income - total_tax_deductions."""
        payload = {
            "title": "Freelance Project Budget",
            "gross_income": 5000.0,
            "items": [
                {"description": "Software Subscriptions", "amount": 120.0},
            ],
            "tax_deductions": [
                {"description": "Self-Employment Tax Estimated", "amount": 750.0},
                {"description": "State Tax Estimated", "amount": 250.0},
            ],
        }
        res = self.client.post("/expenses/", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 201)
        data = res.json()

        # 5000 gross - 1000 deductions = 4000 net
        self.assertEqual(data["gross_income"], 5000.0)
        self.assertEqual(data["total_tax_deductions"], 1000.0)
        self.assertEqual(data["net_income"], 4000.0)
        self.assertEqual(data["total_expenses"], 120.0)
        self.assertEqual(data["remaining_income"], 3880.0)

    def test_add_and_delete_tax_deduction(self):
        """Test adding and deleting a tax deduction from an existing expense."""
        # Create an initial expense
        create_res = self.client.post(
            "/expenses/",
            json={
                "title": "Q3 Financial Plan",
                "gross_income": 8000.0,
                "items": [{"description": "Office Supplies", "amount": 100.0}],
                "tax_deductions": [
                    {"description": "Initial Tax", "amount": 1000.0},
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(create_res.status_code, 201)
        expense_id = create_res.json()["id"]

        # Add new tax deduction
        add_res = self.client.post(
            f"/expenses/{expense_id}/tax-deductions",
            json={"description": "Health Insurance Pre-tax", "amount": 350.0},
            headers=self.headers,
        )
        self.assertEqual(add_res.status_code, 200)
        add_data = add_res.json()
        self.assertEqual(len(add_data["tax_deductions"]), 2)
        self.assertEqual(add_data["total_tax_deductions"], 1350.0)
        # Verify auto-synced net income (8000 - 1350 = 6650)
        self.assertEqual(add_data["net_income"], 6650.0)

        # Delete the added tax deduction
        deduction_id = add_data["tax_deductions"][-1]["id"]
        del_res = self.client.delete(
            f"/expenses/{expense_id}/tax-deductions/{deduction_id}",
            headers=self.headers,
        )
        self.assertEqual(del_res.status_code, 200)
        del_data = del_res.json()
        self.assertEqual(len(del_data["tax_deductions"]), 1)
        self.assertEqual(del_data["total_tax_deductions"], 1000.0)
        self.assertEqual(del_data["net_income"], 7000.0)

    def test_add_and_delete_expense_item(self):
        """Test adding and deleting an expense item from an existing expense."""
        create_res = self.client.post(
            "/expenses/",
            json={
                "title": "Chase Card Expenses",
                "gross_income": 4000.0,
                "items": [{"description": "Dinner", "amount": 80.0}],
            },
            headers=self.headers,
        )
        self.assertEqual(create_res.status_code, 201)
        expense_id = create_res.json()["id"]

        # Add item
        add_res = self.client.post(
            f"/expenses/{expense_id}/items",
            json={"description": "Gas", "amount": 50.0},
            headers=self.headers,
        )
        self.assertEqual(add_res.status_code, 200)
        self.assertEqual(len(add_res.json()["items"]), 2)
        self.assertEqual(add_res.json()["total_expenses"], 130.0)

        # Delete item
        item_id = add_res.json()["items"][-1]["id"]
        del_res = self.client.delete(
            f"/expenses/{expense_id}/items/{item_id}",
            headers=self.headers,
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(len(del_res.json()["items"]), 1)
        self.assertEqual(del_res.json()["total_expenses"], 80.0)

    def test_patch_expense_fields(self):
        """Test updating gross_income, net_income, or title."""
        create_res = self.client.post(
            "/expenses/",
            json={"title": "Old Title", "gross_income": 3000.0, "net_income": 2500.0},
            headers=self.headers,
        )
        expense_id = create_res.json()["id"]

        patch_res = self.client.patch(
            f"/expenses/{expense_id}",
            json={"title": "Updated Title", "gross_income": 3500.0, "net_income": 3000.0},
            headers=self.headers,
        )
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.json()
        self.assertEqual(data["title"], "Updated Title")
        self.assertEqual(data["gross_income"], 3500.0)
        self.assertEqual(data["net_income"], 3000.0)

    def test_get_and_delete_expense(self):
        """Test GET /expenses/{id}, GET /expenses/, and DELETE /expenses/{id}."""
        create_res = self.client.post(
            "/expenses/",
            json={"title": "To be deleted", "gross_income": 1000.0},
            headers=self.headers,
        )
        expense_id = create_res.json()["id"]

        # GET by ID
        get_res = self.client.get(f"/expenses/{expense_id}", headers=self.headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["id"], expense_id)

        # GET list
        list_res = self.client.get("/expenses/", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)
        self.assertTrue(any(e["id"] == expense_id for e in list_res.json()))

        # DELETE
        del_res = self.client.delete(f"/expenses/{expense_id}", headers=self.headers)
        self.assertEqual(del_res.status_code, 204)

        # GET again should return 404
        get_res_after = self.client.get(f"/expenses/{expense_id}", headers=self.headers)
        self.assertEqual(get_res_after.status_code, 404)


if __name__ == "__main__":
    unittest.main()
