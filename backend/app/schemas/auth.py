from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserRead(BaseModel):
    id: str
    username: str
    is_admin: bool = False


class AdminUserRead(BaseModel):
    username: str
    is_admin: bool
    created_at: str
    updated_at: str


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRead]


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    is_admin: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead

