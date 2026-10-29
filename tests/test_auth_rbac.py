"""
Automated Test Suite for HotelPro Authentication, RBAC, and TOTP MFA
PRD Section 4.1 Specifications
"""
import time
import pytest
from app.security.auth import hash_password, verify_password, create_access_token, decode_token
from app.security.totp import totp_service
from app.security.rbac import Role, Permission, has_permission

def test_password_hashing():
    pwd = "EnterpriseSecurePassword2026!"
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

def test_totp_mfa_generation_and_verification():
    secret = totp_service.generate_secret()
    assert len(secret) >= 26
    
    # Generate valid current code
    code = totp_service.get_totp_code(secret)
    assert len(code) == 6
    assert code.isdigit()
    assert totp_service.verify_code(secret, code) is True
    assert totp_service.verify_code(secret, "000000") is False

    # Provisioning URI
    uri = totp_service.get_provisioning_uri(secret, "admin_user")
    assert "otpauth://totp/HotelPro:admin_user" in uri

    # Backup codes
    backup_codes = totp_service.generate_backup_codes(4)
    assert len(backup_codes) == 4
    for bc in backup_codes:
        assert "-" in bc

def test_session_token_and_inactivity_timeout():
    token = create_access_token(
        user_id="usr-123",
        username="frontdesk_lead",
        role="FrontDesk",
        tenant_id="tenant-1",
        mfa_authenticated=True
    )
    payload = decode_token(token)
    assert payload["sub"] == "usr-123"
    assert payload["role"] == "FrontDesk"
    assert payload["mfa_authenticated"] is True

def test_rbac_permissions_matrix():
    # SuperAdmin has all permissions
    assert has_permission(Role.SUPER_ADMIN, Permission.MANAGE_TENANTS) is True
    assert has_permission(Role.SUPER_ADMIN, Permission.CHECK_IN_GUEST) is True
    assert has_permission(Role.SUPER_ADMIN, Permission.EXECUTE_NIGHT_AUDIT) is True

    # FrontDesk has check-in, keycard, folios, but NOT night audit or tenant management
    assert has_permission(Role.FRONT_DESK, Permission.CHECK_IN_GUEST) is True
    assert has_permission(Role.FRONT_DESK, Permission.ENCODE_KEYCARD) is True
    assert has_permission(Role.FRONT_DESK, Permission.POST_INCIDENTAL) is True
    assert has_permission(Role.FRONT_DESK, Permission.EXECUTE_NIGHT_AUDIT) is False
    assert has_permission(Role.FRONT_DESK, Permission.MANAGE_TENANTS) is False

    # Housekeeping can only view and update room cleanliness
    assert has_permission(Role.HOUSEKEEPING, Permission.UPDATE_ROOM_CLEANLINESS) is True
    assert has_permission(Role.HOUSEKEEPING, Permission.VIEW_FOLIO) is False
    assert has_permission(Role.HOUSEKEEPING, Permission.CHECK_IN_GUEST) is False

    # Auditor can execute night audit and view financial reports
    assert has_permission(Role.AUDITOR, Permission.EXECUTE_NIGHT_AUDIT) is True
    assert has_permission(Role.AUDITOR, Permission.SYNC_ERP_JOURNAL) is True
    assert has_permission(Role.AUDITOR, Permission.CHECK_IN_GUEST) is False

