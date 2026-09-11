from pydantic import BaseModel, EmailStr, field_validator


class RegisterStartRequest(BaseModel):
    email: EmailStr


class RegisterVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


class RegisterCompleteRequest(BaseModel):
    verification_token: str
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not (3 <= len(v) <= 32):
            raise ValueError("Username must be 3-32 characters long")
        if not all(c.isalnum() or c in "_-" for c in v):
            raise ValueError("Username may only contain letters, digits, '_' and '-'")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class InviteRequest(BaseModel):
    token: str
    receiver_username: str


class RespondInvitationRequest(BaseModel):
    token: str
    invitation_id: str
    accept: bool


class CancelInvitationRequest(BaseModel):
    token: str
    invitation_id: str
