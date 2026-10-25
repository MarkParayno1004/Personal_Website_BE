# Personal Portfolio API

A robust FastAPI backend powered by PostgreSQL (`psql`), JWT Authentication, Role-Based Access Control (Admin), Expense Tracking, Medication Management, GitHub Repositories Integration, and LinkedIn Event Posts Integration.

---

## Features

### 1. PostgreSQL Database (`psql`)

- SQLAlchemy ORM with connection pooling via `database.py`.
- Configurable with `DATABASE_URL` environment variable:
  ```env
  DATABASE_URL=postgresql+psycopg2://<username>:<password>@localhost:5432/<database_name>
  ```

### 2. Admin Roles Module (`/admin`)

- Protected by administrative privileges (`admin: True`).
- Endpoints:
  - `GET /admin/stats`: High-level statistics (total users, total expenses, total medications, total spend).
  - `GET /admin/users`: View all users and their role assignments.
  - `PATCH /admin/users/{user_id}/role`: Promote or demote user admin privileges.
  - `GET /admin/audit-logs?action=&limit=&offset=`: Audit trail, newest first (logins, logouts, registrations, password changes/resets, email verification, account deletion, role changes, portfolio config/CV changes). Never contains passwords or tokens.

### Pagination

All list endpoints (`/categories/`, `/expenses/`, `/incomes/`, `/medications/`, `/savings/`, `/admin/users`, `/admin/audit-logs`) accept `limit` (default 50, max 100) and `offset` (default 0). The body is still a plain JSON array; the total row count is in the `X-Total-Count` response header (exposed via CORS).

### Account & Email (`/auth`)

- `POST /auth/register`, `POST /auth/login`: return the user plus `token` (send as `Authorization: Bearer <token>`).
- `POST /auth/logout`: revokes every token for the user.
- `PUT /auth/me/password`: change password (returns a fresh token; old tokens are revoked).
- `DELETE /auth/me`: delete the account and its data/files.
- `POST /auth/verify-email/request` (auth): email a verification link (`FRONTEND_URL/verify-email?token=...`, valid 24 h). Sent automatically on register.
- `POST /auth/verify-email/confirm` `{token}`: marks `email_verified`.
- `POST /auth/password-reset/request` `{email}`: always `202` (no account enumeration); emails `FRONTEND_URL/reset-password?token=...` (valid 30 min, single use).
- `POST /auth/password-reset/confirm` `{token, new_password}`: sets the password and revokes all sessions.
- Emails go through [Resend](https://resend.com) (`RESEND_API_KEY`, `EMAIL_FROM`). Without a key, the email (including the link) is logged instead, outside production.
- Unverified users can still log in; `email_verified` is exposed on the user object.

### File Storage & CV Privacy

- With `R2_*` set, files go to Cloudflare R2; otherwise to local disk (`uploads/` is served at `/uploads`, `private_uploads/` is never served).
- Profile pictures are public (`profile_picture` is a full URL).
- CVs are private: the API only exposes `has_cv`. The owner downloads their CV at `GET /auth/me/cv`; admins download the portfolio CV at `GET /portfolio/cv`. Upload/replace/delete via `PUT`/`DELETE` on the same paths.
- Files uploaded before this change (`/uploads/...` paths) must be re-uploaded.

### 3. Expenses & Tax Deductions Module (`/expenses`)

- Create and manage financial sheets, budget plans, and expense collections with gross income, net income, multiple expense items, and multiple tax deductions.
- **Fields**:
  - `title`: Identifier/label (e.g., _"Monthly Budget - March"_ or _"Chase Sapphire Expenses"_).
  - `gross_income`: Total earnings before taxes/deductions (optional, defaults to `0.0`).
  - `net_income`: Income after deductions. Auto-computed as `gross_income - total_tax_deductions` if omitted, or can be explicitly specified.
  - `items`: Array of expense items, each with `description` and `amount`.
  - `tax_deductions`: Array of tax deduction items, each with `description` and `amount`.
- **Endpoints**:
  - `POST /expenses/`: Create an expense sheet with income, multiple expense items, and multiple tax deductions.
  - `GET /expenses/`: List all expense sheets with computed totals (`total_tax_deductions`, `total_expenses`, `remaining_income`).
  - `GET /expenses/{expense_id}`: Retrieve a specific expense sheet with its detailed items and deductions breakdown.
  - `PATCH /expenses/{expense_id}`: Update `title`, `gross_income`, or `net_income`.
  - `POST /expenses/{expense_id}/items`: Add a new expense item.
  - `DELETE /expenses/{expense_id}/items/{item_id}`: Delete a specific expense item.
  - `POST /expenses/{expense_id}/tax-deductions`: Add a new tax deduction item.
  - `DELETE /expenses/{expense_id}/tax-deductions/{deduction_id}`: Delete a specific tax deduction item.
  - `DELETE /expenses/{expense_id}`: Delete an entire expense group and its associated items and tax deductions.

#### Example Payload (`POST /expenses/`):

```json
{
  "title": "Monthly Budget - March 2026",
  "gross_income": 6000.0,
  "net_income": 4500.0,
  "items": [
    { "description": "Apartment Rent", "amount": 1500.0 },
    { "description": "Groceries & Food", "amount": 500.0 },
    { "description": "Utilities & Wifi", "amount": 200.0 }
  ],
  "tax_deductions": [
    { "description": "Federal Income Tax", "amount": 900.0 },
    { "description": "State Income Tax", "amount": 300.0 },
    { "description": "FICA / Social Security", "amount": 300.0 }
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
    { "id": 1, "description": "Apartment Rent", "amount": 1500.0 },
    { "id": 2, "description": "Groceries & Food", "amount": 500.0 },
    { "id": 3, "description": "Utilities & Wifi", "amount": 200.0 }
  ],
  "tax_deductions": [
    { "id": 1, "description": "Federal Income Tax", "amount": 900.0 },
    { "id": 2, "description": "State Income Tax", "amount": 300.0 },
    { "id": 3, "description": "FICA / Social Security", "amount": 300.0 }
  ],
  "created_at": "2026-09-15T00:00:00Z"
}
```

### 4. Medications Module (`/medications`)

- Track medications, their individual cost, and how many doses you have taken.
- Endpoints:
  - `POST /medications/`: Register a medicine with `name`, `cost`, and initial `doses_taken`.
  - `GET /medications/`: List tracked medications with unit cost, doses taken, and total spent (`cost * doses_taken`).
  - `POST /medications/{medication_id}/take`: Quick one-click action to log taking a dose (`doses_taken += 1`).
  - `PATCH /medications/{medication_id}`: Update medication details (e.g., price changes or dose count corrections).
  - `DELETE /medications/{medication_id}`: Remove a medication from tracking.

### 5. GitHub API (`/github`)

- `GET /github/repos?username=...&limit=...`: Fetches public repositories from GitHub's REST API for frontend portfolio display.
- Includes graceful fallback data to keep frontend rendering seamless during development or offline mode.

---

## Quick Start

### 1. Install Dependencies

```powershell
uv sync
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in the values. `DATABASE_URL` and `JWT_SECRET_KEY` are required. Everything else is optional for local development:

| Variable | Purpose |
| --- | --- |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `REDIS_URL` | Cache (e.g. Upstash `rediss://...`); caching is skipped if unreachable |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL` | Cloudflare R2 storage (all five required to enable it) |
| `R2_PRIVATE_BUCKET` | Bucket without public access for CVs (defaults to `R2_BUCKET`) |
| `RESEND_API_KEY`, `EMAIL_FROM` | Transactional email |
| `FRONTEND_URL` | Base URL for email links |

### Deploying (Render + Neon + Upstash + R2)

Start command:

```bash
uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

### 3. Apply Database Migrations

The app no longer creates tables on startup; Alembic owns the schema.

```powershell
uv run alembic upgrade head
```

### 4. Start Development Server

```powershell
uv run fastapi dev main.py
```

Visit the interactive OpenAPI documentation at [http://localhost:8000/docs](http://localhost:8000/docs) (admin accounts only; disabled when `APP_ENV=production`).

### 5. Run Tests

```powershell
uv run python -m unittest discover -s tests -v
```

# Personal_Website_BE
