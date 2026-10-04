import unittest
from schemas import (
    CategoryCreate,
    CategoryResponse,
    ExpenseCreate,
    ExpenseItemCreate,
    ExpenseItemResponse,
    ExpenseResponse,
    ExpenseUpdate,
    MedicationCreate,
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


class TestCategoryAndMedicationSchemas(unittest.TestCase):
    def test_category_create_schema(self):
        cat = CategoryCreate(
            title="Healthcare",
            expenses=[
                ExpenseCreate(
                    title="Insurance",
                    gross_income=500.0,
                    items=[ExpenseItemCreate(description="Premium", amount=200.0)],
                )
            ],
            medications=[
                MedicationCreate(name="Aspirin", cost=5.0, doses_taken=2)
            ],
        )
        self.assertEqual(cat.title, "Healthcare")
        self.assertEqual(len(cat.expenses), 1)
        self.assertEqual(len(cat.medications), 1)
        self.assertEqual(cat.medications[0].name, "Aspirin")

    def test_category_create_schema_with_ids(self):
        cat = CategoryCreate(
            title="Healthcare",
            expense_ids=[1, 2],
            medication_ids=[3, 4],
        )
        self.assertEqual(cat.title, "Healthcare")
        self.assertEqual(cat.expense_ids, [1, 2])
        self.assertEqual(cat.medication_ids, [3, 4])

    def test_category_link_unlink_schemas(self):
        from schemas import CategoryLinkItems, CategoryUnlinkItems, CategoryUpdate
        link_items = CategoryLinkItems(expense_ids=[1, 2], medication_ids=[5])
        self.assertEqual(link_items.expense_ids, [1, 2])
        self.assertEqual(link_items.medication_ids, [5])

        unlink_items = CategoryUnlinkItems(expense_ids=[1])
        self.assertEqual(unlink_items.expense_ids, [1])
        self.assertEqual(unlink_items.medication_ids, [])

        update = CategoryUpdate(title="New", expense_ids=[2], medication_ids=[6])
        self.assertEqual(update.title, "New")
        self.assertEqual(update.expense_ids, [2])
        self.assertEqual(update.medication_ids, [6])

    def test_category_response_schema(self):
        cat_res = CategoryResponse(
            id=1,
            title="Healthcare",
            user_id=123,
            total_expenses_amount=200.0,
            total_medications_amount=10.0,
            total_amount=210.0,
        )
        self.assertEqual(cat_res.id, 1)
        self.assertEqual(cat_res.total_amount, 210.0)

    def test_gross_income_schemas(self):
        from schemas import (
            GrossIncomeCreate,
            GrossIncomeLinkItems,
            GrossIncomeResponse,
            GrossIncomeUnlinkItems,
            GrossIncomeUpdate,
        )
        create = GrossIncomeCreate(
            title="Salary",
            amount=5000.0,
            tax_deductions=[TaxDeductionCreate(description="Tax", amount=1000.0)],
            expense_ids=[1],
            medication_ids=[2],
        )
        self.assertEqual(create.title, "Salary")
        self.assertEqual(create.amount, 5000.0)
        self.assertEqual(len(create.tax_deductions), 1)

        update = GrossIncomeUpdate(title="Bonus", amount=2000.0)
        self.assertEqual(update.title, "Bonus")
        self.assertEqual(update.amount, 2000.0)

        link = GrossIncomeLinkItems(expense_ids=[1, 2], medication_ids=[3])
        self.assertEqual(link.expense_ids, [1, 2])

        unlink = GrossIncomeUnlinkItems(expense_ids=[1])
        self.assertEqual(unlink.expense_ids, [1])

        res = GrossIncomeResponse(
            id=1,
            title="Salary",
            amount=5000.0,
            total_tax_deductions=1000.0,
            net_income=4000.0,
            total_expenses=1500.0,
            total_medications=50.0,
            remaining_income=2450.0,
        )
        self.assertEqual(res.remaining_income, 2450.0)


class TestSavingsSchemas(unittest.TestCase):
    def test_savings_schemas(self):
        from schemas import (
            SavingCreate,
            SavingItemCreate,
            SavingItemResponse,
            SavingLinkExpense,
            SavingResponse,
            SavingUpdate,
        )
        create = SavingCreate(
            title="Emergency Fund",
            expense_id=10,
            items=[SavingItemCreate(description="Initial", amount=500.0)],
        )
        self.assertEqual(create.title, "Emergency Fund")
        self.assertEqual(create.expense_id, 10)
        self.assertEqual(len(create.items), 1)

        update = SavingUpdate(title="Updated Fund", expense_id=None)
        self.assertEqual(update.title, "Updated Fund")
        self.assertIsNone(update.expense_id)

        link = SavingLinkExpense(expense_id=5)
        self.assertEqual(link.expense_id, 5)

        item_res = SavingItemResponse(id=1, saving_id=2, description="Deposit", amount=250.0)
        self.assertEqual(item_res.id, 1)
        self.assertEqual(item_res.amount, 250.0)

        res = SavingResponse(
            id=1,
            title="Emergency Fund",
            expense_id=10,
            user_id=100,
            total_amount=500.0,
            items=[item_res],
        )
        self.assertEqual(res.id, 1)
        self.assertEqual(res.total_amount, 500.0)
        self.assertEqual(len(res.items), 1)


if __name__ == "__main__":
    unittest.main()


