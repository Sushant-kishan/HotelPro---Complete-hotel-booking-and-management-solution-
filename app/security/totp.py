"""
HotelPro Time-Based One-Time Password (TOTP) Module
RFC 6238 compliant MFA implementation per PRD Section 4.1:
Mandatory TOTP for administrative, finance, and front-desk accounts.
"""
import hmac
import hashlib
import time
import base64
import struct
import secrets
from typing import Tuple, List

class TOTPService:
    STEP_SECONDS: int = 30
    DIGITS: int = 6

    @staticmethod
    def generate_secret() -> str:
        """Generates a cryptographically secure 160-bit (20 bytes) Base32 secret."""
        random_bytes = secrets.token_bytes(20)
        return base64.b32encode(random_bytes).decode("utf-8").replace("=", "")

    @staticmethod
    def generate_backup_codes(count: int = 8) -> List[str]:
        """Generates single-use emergency alphanumeric recovery codes."""
        codes = []
        for _ in range(count):
            token = secrets.token_hex(4).upper() # e.g. A3F8-29BC
            codes.append(f"{token[:4]}-{token[4:]}")
        return codes

    @classmethod
    def get_totp_code(cls, secret: str, time_step: int = None) -> str:
        """Generates the 6-digit TOTP code for a given secret at current or specified time step."""
        if time_step is None:
            time_step = int(time.time()) // cls.STEP_SECONDS
            
        # Ensure base32 padding
        padded_secret = secret.upper()
        missing_padding = len(padded_secret) % 8
        if missing_padding:
            padded_secret += "=" * (8 - missing_padding)
            
        key = base64.b32decode(padded_secret)
        msg = struct.pack(">Q", time_step)
        
        # RFC 4226 / 6238 HMAC-SHA1
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        binary = (
            ((h[offset] & 0x7F) << 24)
            | ((h[offset + 1] & 0xFF) << 16)
            | ((h[offset + 2] & 0xFF) << 8)
            | (h[offset + 3] & 0xFF)
        )
        otp = binary % (10 ** cls.DIGITS)
        return str(otp).zfill(cls.DIGITS)

    @classmethod
    def verify_code(cls, secret: str, code: str, allowed_skew_steps: int = 1) -> bool:
        """
        Verifies a user-provided 6-digit code against the secret.
        Allows +/- 1 interval (30 seconds before/after) to account for clock skew.
        """
        if not secret or not code:
            return False
        cleaned_code = code.strip().replace(" ", "")
        current_step = int(time.time()) // cls.STEP_SECONDS
        
        for offset in range(-allowed_skew_steps, allowed_skew_steps + 1):
            if cls.get_totp_code(secret, current_step + offset) == cleaned_code:
                return True
        return False

    @staticmethod
    def get_provisioning_uri(secret: str, username: str, issuer: str = "HotelPro") -> str:
        """Generates otpauth:// URI for authenticator apps (Google Authenticator, Authy, etc.)."""
        return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"

totp_service = TOTPService()

