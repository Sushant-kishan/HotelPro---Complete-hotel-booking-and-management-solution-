"""
HotelPro Authentication & User API Router
PRD Section 4.1: RBAC, MFA (TOTP), Session Inactivity, Audit Logging.
"""
import uuid
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, status

from app.database import get_db
from app.security.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_permission
)
from app.security.totp import totp_service
from app.security.rbac import Role, Permission
from app.security.audit import audit_service

router = APIRouter(prefix="/auth", tags=["Authentication & RBAC"])

class LoginRequest(BaseModel):
    username: str
    password: str

class TOTPVerifyRequest(BaseModel):
    username: str
    totp_code: str

class UserCreateRequest(BaseModel):
    username: str
    email: str
    full_name: str
    password: str
    role: Role
    property_id: Optional[str] = None

@router.post("/login")
def login(req: LoginRequest):
    """
    Standard staff login endpoint.
    If TOTP MFA is enabled on the account (mandatory for administrative/front-desk/finance),
    returns mfa_required=True and a temporary pre-auth challenge.
    """
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (req.username,)).fetchone()
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")

        # Update last login timestamp
        db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))

        # Check if user requires MFA
        if user["totp_enabled"] == 1:
            return {
                "mfa_required": True,
                "username": user["username"],
                "message": "TOTP MFA code required to complete authentication (PRD Section 4.1)."
            }

        # Otherwise issue full token (e.g. Housekeeping)
        token = create_access_token(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            tenant_id=user["tenant_id"],
            property_id=user["property_id"],
            mfa_authenticated=False
        )

        audit_service.log_event(
            tenant_id=user["tenant_id"],
            property_id=user["property_id"],
            user_id=user["id"],
            user_role=user["role"],
            action="USER_LOGIN",
            entity_type="User",
            entity_id=user["id"],
            payload={"mfa": False}
        )

        return {
            "mfa_required": False,
            "access_token": token,
            "token_type": "bearer",
            "expires_in_minutes": 15,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
                "property_id": user["property_id"]
            }
        }

@router.post("/mfa/verify")
def verify_mfa(req: TOTPVerifyRequest):
    """Verifies RFC 6238 TOTP 6-digit code or emergency backup code."""
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (req.username,)).fetchone()
        if not user or user["totp_enabled"] != 1:
            raise HTTPException(status_code=400, detail="MFA not configured for user.")

        # Check standard TOTP code
        code_valid = totp_service.verify_code(user["totp_secret"], req.totp_code)

        # If not, check backup codes
        if not code_valid and user["backup_codes"]:
            backup_list = json.loads(user["backup_codes"])
            if req.totp_code in backup_list:
                code_valid = True
                backup_list.remove(req.totp_code)
                db.execute("UPDATE users SET backup_codes = ? WHERE id = ?", (json.dumps(backup_list), user["id"]))

        if not code_valid:
            raise HTTPException(status_code=401, detail="Invalid TOTP code or expired token.")

        # Issue full MFA-authenticated token
        token = create_access_token(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            tenant_id=user["tenant_id"],
            property_id=user["property_id"],
            mfa_authenticated=True
        )

        audit_service.log_event(
            tenant_id=user["tenant_id"],
            property_id=user["property_id"],
            user_id=user["id"],
            user_role=user["role"],
            action="MFA_AUTHENTICATED",
            entity_type="User",
            entity_id=user["id"],
            payload={"method": "TOTP"}
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in_minutes": 15,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
                "property_id": user["property_id"],
                "mfa_authenticated": True
            }
        }

@router.get("/mfa/setup")
def setup_mfa(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generates new TOTP secret, provisioning URI, and emergency backup codes for staff account."""
    secret = totp_service.generate_secret()
    uri = totp_service.get_provisioning_uri(secret, current_user["username"])
    backup_codes = totp_service.generate_backup_codes()

    with get_db() as db:
        db.execute(
            "UPDATE users SET totp_secret = ?, backup_codes = ?, totp_enabled = 1 WHERE id = ?",
            (secret, json.dumps(backup_codes), current_user["id"])
        )

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "backup_codes": backup_codes,
        "message": "Scan provisioning URI with Google Authenticator or enter base32 secret."
    }

@router.get("/me")
def get_current_user_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns profile and role permissions of current user."""
    from app.security.rbac import ROLE_PERMISSIONS, Role
    role_enum = Role(current_user["role"])
    perms = [p.value for p in ROLE_PERMISSIONS.get(role_enum, set())]
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "full_name": current_user["full_name"],
        "role": current_user["role"],
        "property_id": current_user["property_id"],
        "totp_enabled": bool(current_user["totp_enabled"]),
        "mfa_authenticated": current_user.get("mfa_authenticated", False),
        "permissions": perms
    }
