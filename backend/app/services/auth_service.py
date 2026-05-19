import sqlite3

from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse, UserRead


class AuthService:
    def __init__(self, conn: sqlite3.Connection):
        self.users = UserRepository(conn)
        self.users.initialize()

    def create_user(self, username: str, password: str) -> UserRead:
        clean_username = username.strip()
        if not clean_username or not password:
            raise ValueError("Username and password are required")

        self.users.upsert_user(clean_username, hash_password(password))
        return UserRead(id=clean_username, username=clean_username)

    def authenticate(self, username: str, password: str) -> LoginResponse | None:
        clean_username = username.strip()
        if not clean_username or not password:
            return None

        row = self.users.get_by_username(clean_username)
        if row is None:
            return None
        if not verify_password(password, row["password_hash"]):
            return None

        user = UserRead(id=row["username"], username=row["username"])
        return LoginResponse(access_token=create_access_token(user.id), user=user)

    def get_user(self, username: str) -> UserRead | None:
        row = self.users.get_by_username(username)
        if row is None:
            return None
        return UserRead(id=row["username"], username=row["username"])

