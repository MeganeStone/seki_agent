import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.postgres import connect
from app.core.config import get_settings
from app.services.auth_service import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a Seki Agent backend user.")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--admin", action="store_true", help="grant admin privileges")
    args = parser.parse_args()

    with connect() as conn:
        user = AuthService(conn).create_user(
            args.username,
            args.password,
            is_admin=True if args.admin else None,
        )

    print(f"Created or updated user: {user.username} (admin={user.is_admin})")
    print(f"Database: {get_settings().database_url}")


if __name__ == "__main__":
    main()
