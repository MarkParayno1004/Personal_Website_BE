# Personal Portfolio API

A robust FastAPI backend powered by PostgreSQL (`psql`), JWT Authentication, Role-Based Access Control (Admin), Expense Tracking, Medication Management, GitHub Repositories Integration, and LinkedIn Event Posts Integration.

---

## Features

### 1. PostgreSQL Database (`psql`)
* SQLAlchemy ORM with connection pooling via `database.py`.
* Configurable with `DATABASE_URL` environment variable:
  ```env
  DATABASE_URL=postgresql+psycopg2://<username>:<password>@localhost:5432/<database_name>
  ```

### 2. Admin Roles Module (`/admin`)
* Protected by administrative privileges (`admin: True`).
* Endpoints:
  * `GET /admin/stats`: High-level statistics (total users, total expenses, total medications, total spend).
  * `GET /admin/users`: View all users and their role assignments.
  * `PATCH /admin/users/{user_id}/role`: Promote or demote user admin privileges.

### 3. Expenses & Tax Deductions Module (`/expenses`)
* Create and manage financial sheets, budget plans, and expense collections with gross income, net income, multiple expense items, and multiple tax deductions.
* **Fields**:
  * `title`: Identifier/label (e.g., *"Monthly Budget - March"* or *"Chase Sapphire Expenses"*).
  * `gross_income`: Total earnings before taxes/deductions (optional, defaults to `0.0`).
  * `net_income`: Income after deductions. Auto-computed as `gross_income - total_tax_deductions` if omitted, or can be explicitly specified.
  * `items`: Array of expense items, each with `description` and `amount`.
  * `tax_deductions`: Array of tax deduction items, each with `description` and `amount`.
* **Endpoints**:
  * `POST /expenses/`: Create an expense sheet with income, multiple expense items, and multiple tax deductions.
  * `GET /expenses/`: List all expense sheets with computed totals (`total_tax_deductions`, `total_expenses`, `remaining_income`).
  * `GET /expenses/{expense_id}`: Retrieve a specific expense sheet with its detailed items and deductions breakdown.
  * `PATCH /expenses/{expense_id}`: Update `title`, `gross_income`, or `net_income`.
  * `POST /expenses/{expense_id}/items`: Add a new expense item.
  * `DELETE /expenses/{expense_id}/items/{item_id}`: Delete a specific expense item.
  * `POST /expenses/{expense_id}/tax-deductions`: Add a new tax deduction item.
  * `DELETE /expenses/{expense_id}/tax-deductions/{deduction_id}`: Delete a specific tax deduction item.
  * `DELETE /expenses/{expense_id}`: Delete an entire expense group and its associated items and tax deductions.

#### Example Payload (`POST /expenses/`):
```json
{
  "title": "Monthly Budget - March 2026",
  "gross_income": 6000.0,
  "net_income": 4500.0,
  "items": [
    {"description": "Apartment Rent", "amount": 1500.0},
    {"description": "Groceries & Food", "amount": 500.0},
    {"description": "Utilities & Wifi", "amount": 200.0}
  ],
  "tax_deductions": [
    {"description": "Federal Income Tax", "amount": 900.0},
    {"description": "State Income Tax", "amount": 300.0},
    {"description": "FICA / Social Security", "amount": 300.0}
  ]
}
```

#### Example Response:
```json
{
  "id": 1,
  "title": "Monthly Budget - March 2026",
  "gross_income": 6000.0,
  "net_income": 4500.0,
  "total_tax_deductions": 1500.0,
  "total_expenses": 2200.0,
  "total_amount": 2200.0,
  "remaining_income": 2300.0,
  "items": [
    {"id": 1, "description": "Apartment Rent", "amount": 1500.0},
    {"id": 2, "description": "Groceries & Food", "amount": 500.0},
    {"id": 3, "description": "Utilities & Wifi", "amount": 200.0}
  ],
  "tax_deductions": [
    {"id": 1, "description": "Federal Income Tax", "amount": 900.0},
    {"id": 2, "description": "State Income Tax", "amount": 300.0},
    {"id": 3, "description": "FICA / Social Security", "amount": 300.0}
  ],
  "created_at": "2026-09-15T00:00:00Z"
}
```

### 4. Medications Module (`/medications`)
* Track medications, their individual cost, and how many doses you have taken.
* Endpoints:
  * `POST /medications/`: Register a medicine with `name`, `cost`, and initial `doses_taken`.
  * `GET /medications/`: List tracked medications with unit cost, doses taken, and total spent (`cost * doses_taken`).
  * `POST /medications/{medication_id}/take`: Quick one-click action to log taking a dose (`doses_taken += 1`).
  * `PATCH /medications/{medication_id}`: Update medication details (e.g., price changes or dose count corrections).
  * `DELETE /medications/{medication_id}`: Remove a medication from tracking.

### 5. GitHub API (`/github`)
* `GET /github/repos?username=...&limit=...`: Fetches public repositories from GitHub's REST API for frontend portfolio display.
* Includes graceful fallback data to keep frontend rendering seamless during development or offline mode.

### 6. LinkedIn API (`/linkedin`)
* `GET /linkedin/posts?limit=...`: Fetches recent event posts, announcements, and talks from LinkedIn.
* Supports `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN` with rich structured event fallbacks.

---

## Quick Start

### 1. Install Dependencies
```powershell
uv sync
# or
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional)
Create a `.env` file in the project root:
```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/personal_portfolio
JWT_SECRET_KEY=your_secure_32_byte_secret_key_here
GITHUB_USERNAME=MarkParayno1004
GITHUB_TOKEN=your_optional_github_pat
LINKEDIN_ACCESS_TOKEN=your_optional_linkedin_token
LINKEDIN_AUTHOR_URN=urn:li:person:YOUR_URN
```

### 3. Start Development Server
```powershell
fastapi dev main.py
```
Visit the interactive OpenAPI documentation at [http://localhost:8000/docs](http://localhost:8000/docs).
# Personal_Website_BE
