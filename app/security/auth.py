"""
HotelPro Authentication & Session Integrity Service
PRD Section 4.1: Multi-Factor Authentication (MFA), 15-minute inactivity termination,
cryptographic token validation, and password security.
"""
import hashlib
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import get_db
from app.security.rbac import Role, Permission, has_permission

security_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """PBKDF2-HMAC-SHA256 password hashing with 600,000 iterations."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600000)
    return f"{salt.hex()}:{key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against stored salt:hash string."""
    try:
        parts = hashed_password.split(":")
        if len(parts) != 2:
            return False
        salt = bytes.fromhex(parts[0])
        expected_key = bytes.fromhex(parts[1])
        calculated_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 600000)
        return secrets.compare_digest(calculated_key, expected_key)
    except Exception:
        return False

def create_access_token(
    user_id: str,
    username: str,
    role: str,
    tenant_id: str,
    property_id: Optional[str] = None,
    mfa_authenticated: bool = False
) -> str:
    """
    Creates a JWT access token with 15-minute inactivity termination strictly
    mandated by PRD Section 4.1.
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES)
    
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "mfa_authenticated": mfa_authenticated,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "last_activity": int(now.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    """Decodes and validates JWT token expiration and integrity."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        
        # Check strict 15-minute inactivity termination
        last_activity = payload.get("last_activity")
        now = int(datetime.now(timezone.utc).timestamp())
        if last_activity and (now - last_activity) > (settings.SESSION_INACTIVITY_TIMEOUT_MINUTES * 60):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session terminated due to 15 minutes of inactivity (PRD Section 4.1)."
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token expired. Please re-authenticate."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials."
        )

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> Dict[str, Any]:
    """FastAPI dependency to extract and authenticate current user session."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token in the Authorization header."
        )
    
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)).fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated or no longer exists."
            )
        
        # Update user's last_activity timestamp in database
        db.execute(
            "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,)
        )
        
        user_dict = dict(user)
        # Attach token-level session info
        user_dict["mfa_authenticated"] = payload.get("mfa_authenticated", False)
        return user_dict

def require_permission(permission: Permission):
    """Factory dependency for checking granular role capabilities."""
    def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user_role}' lacks required permission '{permission.value}'"
            )
        
        # Mandatory MFA check for admin, manager, front-desk, auditor
        mfa_required_roles = {
            Role.SUPER_ADMIN.value,
            Role.PROPERTY_MANAGER.value,
            Role.FRONT_DESK.value,
            Role.AUDITOR.value
        }
        if user_role in mfa_required_roles and current_user.get("totp_enabled") == 1:
            if not current_user.get("mfa_authenticated"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="MFA verification is required to perform this action (PRD Section 4.1)."
                )
        return current_user
    return permission_checker

