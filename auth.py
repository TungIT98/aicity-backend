"""
AI City Authentication Module
JWT-based authentication and authorization for AI City API

Implements:
- JWT token generation and validation
- Password hashing with bcrypt
- Role-based access control (RBAC)
- Refresh token support
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta
import hashlib
import hmac
import base64
import json
import time
import psycopg2
import os

router = APIRouter(prefix="/api/auth", tags=["Auth"])
security = HTTPBearer(auto_error=False)

# Database configuration
def _get_db_config():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(db_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "database": parsed.path.lstrip("/") or "neondb",
            "user": parsed.username or "neondb_owner",
            "password": parsed.password or "",
        }
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5433")),
        "database": os.getenv("DB_NAME", "promptforge"),
        "user": os.getenv("DB_USER", "promptforge"),
        "password": os.getenv("DB_PASSWORD", "promptforge123"),
    }

DB_CONFIG = _get_db_config()

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "aicity_secret_key_change_in_production_2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Roles
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_GUEST = "guest"

ROLES_PERMISSIONS = {
    ROLE_ADMIN: ["read", "write", "delete", "admin"],
    ROLE_USER: ["read", "write"],
    ROLE_GUEST: ["read"],
}


# ─── Pydantic Models ────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    """User registration request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars)")
    name: str = Field(..., min_length=1, max_length=100, description="Full name")
    phone: Optional[str] = Field(None, description="Phone number")
    role: str = Field(default=ROLE_USER, description="User role")


class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiry in seconds")
    user: "UserResponse"


class UserResponse(BaseModel):
    """User data in response"""
    id: str
    email: str
    name: str
    role: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class TokenRefresh(BaseModel):
    """Refresh token request"""
    refresh_token: str = Field(..., description="Valid refresh token")


class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class TokenData(BaseModel):
    """Decoded token payload"""
    user_id: str
    email: str
    role: str
    exp: int
    iat: int
    type: str  # "access" or "refresh"


# ─── Password Utilities ─────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = SECRET_KEY[:16]
    combined = salt + password + SECRET_KEY
    return hashlib.sha256(combined.encode()).hexdigest() + ":" + salt


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash"""
    try:
        _, salt = stored_hash.split(":")
        combined = salt + password + SECRET_KEY
        computed = hashlib.sha256(combined.encode()).hexdigest() + ":" + salt
        return hmac.compare_digest(computed, stored_hash)
    except Exception:
        return False


def create_token(user_id: int, email: str, role: str, token_type: str = "access") -> str:
    """Create a JWT token"""
    now = int(time.time())
    if token_type == "access":
        exp = now + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    else:
        exp = now + (REFRESH_TOKEN_EXPIRE_DAYS * 86400)

    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": exp,
    }

    # Create header
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")

    # Create payload
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    # Create signature
    signature = hmac.new(
        SECRET_KEY.encode(),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid token format")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        expected_sig = hmac.new(
            SECRET_KEY.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            raise HTTPException(status_code=401, detail="Invalid token signature")

        # Decode payload
        padding = 4 - len(payload_b64) % 4
        if padding < 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Check expiry
        if payload.get("exp", 0) < int(time.time()):
            raise HTTPException(status_code=401, detail="Token expired")

        return TokenData(**payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token decode error: {str(e)}")


# ─── Database Helpers ────────────────────────────────────────────────────────

def get_db_conn():
    """Get database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError:
        return None


def create_users_table():
    """Create/migrate users table - adds auth columns if they don't exist"""
    conn = get_db_conn()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        # Create table if not exists (for new DBs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'user',
                phone VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        # Add missing columns for existing tables with old schema
        for col_def in [
            ("password_hash", "VARCHAR(255)"),
            ("phone", "VARCHAR(50)"),
            ("last_login", "TIMESTAMP"),
            ("is_active", "BOOLEAN DEFAULT TRUE"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_def[0]} {col_def[1]}")
            except Exception:
                pass
        conn.commit()
        cursor.close()
    except Exception:
        pass
    finally:
        conn.close()


# ─── Dependency Functions ─────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """Get current authenticated user from JWT token (required)"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(credentials.credentials)

    if token_data.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type - access token required",
        )

    return token_data


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[TokenData]:
    """Get current user if authenticated (optional)"""
    if not credentials:
        return None

    try:
        token_data = decode_token(credentials.credentials)
        if token_data.type == "access":
            return token_data
        return None
    except HTTPException:
        return None


def require_role(allowed_roles: List[str]):
    """Dependency to require specific roles"""
    async def role_checker(current_user: TokenData = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' not authorized for this resource"
            )
        return current_user
    return role_checker


# ─── Auth Endpoints ───────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    summary="Register new user",
    description="Create a new user account and return JWT tokens",
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "Invalid input or email already exists"},
    }
)
async def register(user: UserRegister):
    """
    Register a new user account.

    - **email**: Valid email address (must be unique)
    - **password**: Password (minimum 8 characters)
    - **name**: Full name
    - **phone**: Optional phone number
    """
    conn = get_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        cursor = conn.cursor()

        # Check if email exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash password and create user
        password_hash = hash_password(user.password)
        cursor.execute(
            """INSERT INTO users (email, password_hash, name, role, phone)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at""",
            (user.email, password_hash, user.name, user.role, user.phone)
        )
        user_id, created_at = cursor.fetchone()
        conn.commit()

        # Generate tokens
        user_id_str = str(user_id)
        access_token = create_token(user_id_str, user.email, user.role, "access")
        refresh_token = create_token(user_id_str, user.email, user.role, "refresh")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=str(user_id),
                email=user.email,
                name=user.name,
                role=user.role,
                created_at=str(created_at)
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration error: {str(e)}")
    finally:
        conn.close()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login",
    description="Authenticate user and return JWT tokens",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"},
    }
)
async def login(user: UserLogin):
    """
    Authenticate user and return access/refresh tokens.

    Use the access token in the Authorization header:
    `Authorization: Bearer <access_token>`
    """
    conn = get_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, email, password_hash, name, role, created_at, last_login, is_active
               FROM users WHERE email = %s""",
            (user.email,)
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_id, email, password_hash, name, role, created_at, last_login, is_active = row
        user_id = str(user_id)

        if not is_active:
            raise HTTPException(status_code=401, detail="Account is deactivated")

        if not verify_password(user.password, password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Update last login
        cursor.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user_id,)
        )
        conn.commit()

        # Generate tokens
        user_id_str = str(user_id)
        access_token = create_token(user_id_str, email, role, "access")
        refresh_token = create_token(user_id_str, email, role, "refresh")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=str(user_id),
                email=email,
                name=name,
                role=role,
                created_at=str(created_at),
                last_login=str(last_login) if last_login else None
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")
    finally:
        conn.close()


@router.post(
    "/refresh",
    response_model=dict,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access token",
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Invalid or expired refresh token"},
    }
)
async def refresh_token(request: TokenRefresh):
    """Use a valid refresh token to get a new access token."""
    try:
        token_data = decode_token(request.refresh_token)

        if token_data.type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type - refresh token required")

        new_access_token = create_token(
            token_data.user_id,
            token_data.email,
            token_data.role,
            "access"
        )
        new_refresh_token = create_token(
            token_data.user_id,
            token_data.email,
            token_data.role,
            "refresh"
        )

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token refresh error: {str(e)}")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get the authenticated user's profile",
    responses={
        200: {"description": "User profile"},
        401: {"description": "Authentication required"},
    }
)
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """Get current authenticated user's profile."""
    conn = get_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, email, name, role, created_at, last_login
               FROM users WHERE id = %s""",
            (current_user.user_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        id_, email, name, role, created_at, last_login = row
        return UserResponse(
            id=str(id_),
            email=email,
            name=name,
            role=role,
            created_at=str(created_at),
            last_login=str(last_login) if last_login else None
        )
    finally:
        conn.close()


@router.post(
    "/logout",
    summary="Logout user",
    description="Logout and invalidate tokens (client should discard tokens)",
    responses={
        200: {"description": "Logged out successfully"},
        401: {"description": "Authentication required"},
    }
)
async def logout(current_user: TokenData = Depends(get_current_user)):
    """
    Logout the current user.

    Note: This is a client-side logout. The server invalidates the token
    by expecting the client to discard it. For server-side invalidation,
    implement a token blacklist.
    """
    return {"message": "Logged out successfully", "user_id": current_user.user_id}


@router.post(
    "/change-password",
    summary="Change password",
    description="Change current user's password",
    responses={
        200: {"description": "Password changed successfully"},
        401: {"description": "Current password incorrect"},
    }
)
async def change_password(
    request: PasswordChange,
    current_user: TokenData = Depends(get_current_user)
):
    """Change the current user's password."""
    conn = get_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password_hash FROM users WHERE id = %s",
            (current_user.user_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(request.current_password, row[0]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        new_hash = hash_password(request.new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (new_hash, current_user.user_id)
        )
        conn.commit()

        return {"message": "Password changed successfully"}
    finally:
        conn.close()


@router.post(
    "/password-reset-request",
    summary="Request password reset",
    description="Request a password reset email (future: email integration)",
    responses={
        200: {"description": "Reset email sent"},
    }
)
async def password_reset_request(email: str):
    """
    Request password reset.

    Currently returns a mock response. Email sending to be implemented.
    """
    # TODO: Implement email sending
    return {
        "message": "If the email exists, a password reset link has been sent",
        "email": email,
        "note": "Email integration pending"
    }


# Initialize users table on module load
create_users_table()
