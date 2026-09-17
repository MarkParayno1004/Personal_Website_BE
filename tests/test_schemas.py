import unittest
from schemas import (
    ExpenseCreate,
    ExpenseItemCreate,
    ExpenseItemResponse,
    ExpenseResponse,
    ExpenseUpdate,
    TaxDeductionCreate,
    TaxDeductionResponse,
    User,
    UserCreate,
    UserPublic,
)


class TestUserSchemas(unittest.TestCase):
    def setUp(self):
        # Migrated example test data from schemas.py
        self.external_data = {
            "id": 123,
            "token": "testTokendawdawdwdaw",
            "first_name": "test name",
            "last_name": "test last name",
            "email": "test@test.com",
            "password": "123",
        }

    def test_user_instantiation(self):
        """Test that the full User model instantiates properly with example data."""
        user = User(**self.external_data)
        self.assertEqual(user.id, 123)
        self.assertEqual(user.token, "testTokendawdawdwdaw")
        self.assertEqual(user.first_name, "test name")
        self.assertEqual(user.last_name, "test last name")
        self.assertEqual(user.email, "test@test.com")
        self.assertEqual(user.password, "123")

    def test_user_public_excludes_password(self):
        """Test that UserPublic does not expose password."""
        public_user = UserPublic(**self.external_data)
        dumped = public_user.model_dump()
        self.assertNotIn("password", dumped)
        self.assertEqual(dumped["id"], 123)
        self.assertEqual(dumped["email"], "test@test.com")

    def test_user_create_requires_password(self):
        """Test that UserCreate accepts password for registration."""
        create_data = {
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "password": "secret_password",
        }
        create_user = UserCreate(**create_data)
        self.assertEqual(create_user.password, "secret_password")


class TestExpenseAndTaxSchemas(unittest.TestCase):
    def test_expense_create_with_tax_deductions_and_income(self):
        """Test that ExpenseCreate accepts gross_income, net_income, items, and tax_deductions."""
        payload = {
            "title": "Monthly Budget - March",
            "gross_income": 6000.0,
            "net_income": 4500.0,
            "items": [
                {"description": "Rent", "amount": 1500.0},
                {"description": "Groceries", "amount": 400.0},
            ],
            "tax_deductions": [
                {"description": "Federal Tax", "amount": 900.0},
                {"description": "State Tax", "amount": 300.0},
                {"description": "FICA / Social Security", "amount": 300.0},
            ],
        }
        expense = ExpenseCreate(**payload)
        self.assertEqual(expense.title, "Monthly Budget - March")
        self.assertEqual(expense.gross_income, 6000.0)
        self.assertEqual(expense.net_income, 4500.0)
        self.assertEqual(len(expense.items), 2)
        self.assertEqual(len(expense.tax_deductions), 3)
        self.assertEqual(expense.items[0].description, "Rent")
        self.assertEqual(expense.tax_deductions[0].description, "Federal Tax")

    def test_expense_response_fields(self):
        """Test that ExpenseResponse formats all income and deduction breakdown fields."""
        res_data = {
            "id": 1,
            "title": "Monthly Budget - March",
            "gross_income": 6000.0,
            "net_income": 4500.0,
            "total_tax_deductions": 1500.0,
            "total_expenses": 1900.0,
            "total_amount": 1900.0,
            "remaining_income": 2600.0,
            "items": [
                {"id": 10, "description": "Rent", "amount": 1500.0},
                {"id": 11, "description": "Groceries", "amount": 400.0},
            ],
            "tax_deductions": [
                {"id": 20, "description": "Federal Tax", "amount": 900.0},
                {"id": 21, "description": "State Tax", "amount": 300.0},
            ],
        }
        expense_res = ExpenseResponse(**res_data)
        self.assertEqual(expense_res.id, 1)
        self.assertEqual(expense_res.gross_income, 6000.0)
        self.assertEqual(expense_res.net_income, 4500.0)
        self.assertEqual(expense_res.total_tax_deductions, 1500.0)
        self.assertEqual(expense_res.total_expenses, 1900.0)
        self.assertEqual(expense_res.total_amount, 1900.0)
        self.assertEqual(expense_res.remaining_income, 2600.0)
        self.assertEqual(len(expense_res.items), 2)
        self.assertEqual(len(expense_res.tax_deductions), 2)

    def test_expense_update_schema(self):
        """Test partial updates with ExpenseUpdate."""
        update = ExpenseUpdate(gross_income=7000.0)
        self.assertEqual(update.gross_income, 7000.0)
        self.assertIsNone(update.title)
        self.assertIsNone(update.net_income)


if __name__ == "__main__":
    unittest.main()
