import psycopg

from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse, UserRead


class AuthService:
    def __init__(self, conn: psycopg.Connection):
        self.users = UserRepository(conn)
        self.users.initialize()

    def create_user(self, username: str, password: str, is_admin: bool | None = None) -> UserRead:
        clean_username = username.strip()
        if not clean_username or not password:
            raise ValueError("Username and password are required")

        self.users.upsert_user(clean_username, hash_password(password), is_admin=is_admin)
        user = self.get_user(clean_username)
        if user is None:
            raise RuntimeError("Failed to create user")
        return user

    def authenticate(self, username: str, password: str) -> LoginResponse | None:
        clean_username = username.strip()
        if not clean_username or not password:
            return None

        row = self.users.get_by_username(clean_username)
        if row is None:
            return None
        if not verify_password(password, row["password_hash"]):
            return None

        user = self._to_user(row)
        return LoginResponse(access_token=create_access_token(user.id), user=user)

    def get_user(self, username: str) -> UserRead | None:
        row = self.users.get_by_username(username)
        if row is None:
            return None
        return self._to_user(row)

    @staticmethod
    def _to_user(row: dict) -> UserRead:
        return UserRead(
            id=row["username"],
            username=row["username"],
            is_admin=bool(row.get("is_admin", False)),
        )
