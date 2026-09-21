import argparse
import getpass
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import SessionLocal
from models import User
from security import hash_password


def create_or_promote_admin(email: str, first_name: str, last_name: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            print(f"User with email '{email}' already exists.")
            if not user.admin:
                user.admin = True
                if password:
                    user.hashed_password = hash_password(password)
                db.commit()
                print(f"Successfully promoted '{email}' to administrator!")
            else:
                if password:
                    user.hashed_password = hash_password(password)
                    db.commit()
                    print(f"Password updated for existing admin '{email}'.")
                else:
                    print(f"User '{email}' is already an administrator.")
            return

        # Create new admin user
        admin_user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            hashed_password=hash_password(password),
            admin=True,
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"Successfully created admin user: {email} (ID: {admin_user.id})")
    except Exception as e:
        db.rollback()
        print(f"Error creating admin user: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Create or promote an administrator user.")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--first-name", help="Admin first name")
    parser.add_argument("--last-name", help="Admin last name")
    parser.add_argument("--password", help="Admin password (plain text)")

    args = parser.parse_args()

    email = args.email or input("Admin Email: ").strip()
    if not email:
        print("Email is required.", file=sys.stderr)
        sys.exit(1)

    first_name = args.first_name or input("First Name [Admin]: ").strip() or "Admin"
    last_name = args.last_name or input("Last Name [User]: ").strip() or "User"

    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm Password: ")
        if password != password_confirm:
            print("Passwords do not match.", file=sys.stderr)
            sys.exit(1)

    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    create_or_promote_admin(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )


if __name__ == "__main__":
    main()
