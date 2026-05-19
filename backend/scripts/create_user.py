import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.sqlite import connect
from app.services.auth_service import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a Seki Agent backend user.")
    parser.add_argument("username")
    parser.add_argument("password")
    args = parser.parse_args()

    with connect() as conn:
        user = AuthService(conn).create_user(args.username, args.password)

    print(f"Created or updated user: {user.username}")


if __name__ == "__main__":
    main()
