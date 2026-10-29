"""
HotelPro Field-Level AES-256 Encryption & Blind Indexing Module
PRD Section 4.1: Field-level AES-256 encryption for guest PII, strict GDPR/CCPA
data export and right-to-erasure compliance, least-privilege DB access.
"""
import os
import hmac
import hashlib
import json
import base64
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings

class PIIEncryptionService:
    def __init__(self, key: bytes = settings.AES_ENCRYPTION_KEY, blind_salt: str = settings.BLIND_INDEX_SALT):
        # AES-GCM requires a 128, 192, or 256-bit key (32 bytes for AES-256)
        if len(key) != 32:
            key = hashlib.sha256(key).digest()
        self.key = key
        self.blind_salt = blind_salt.encode("utf-8")
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypts plaintext string with AES-256-GCM returning base64 string (nonce + ciphertext)."""
        if not plaintext:
            return ""
        nonce = os.urandom(12) # 96-bit standard nonce for AES-GCM
        data = plaintext.encode("utf-8")
        ciphertext = self.aesgcm.encrypt(nonce, data, None)
        # Store as base64: nonce (12 bytes) + ciphertext + tag (16 bytes)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, encrypted_b64: str) -> str:
        """Decrypts base64 encoded AES-256-GCM payload."""
        if not encrypted_b64:
            return ""
        try:
            raw = base64.b64decode(encrypted_b64.encode("utf-8"))
            if len(raw) < 28: # 12 bytes nonce + 16 bytes tag minimum
                return "[ENCRYPTED]"
            nonce = raw[:12]
            ciphertext = raw[12:]
            decrypted = self.aesgcm.decrypt(nonce, ciphertext, None)
            return decrypted.decode("utf-8")
        except Exception:
            return "[CORRUPTED_OR_SHREDDED_PII]"

    def compute_blind_index(self, value: str) -> str:
        """
        Computes a deterministic HMAC-SHA256 blind index.
        Allows exact-match database queries on encrypted values (e.g. email, phone)
        without exposing plaintext or compromising ciphertext randomness.
        """
        if not value:
            return ""
        normalized = value.strip().lower().encode("utf-8")
        h = hmac.new(self.blind_salt, normalized, hashlib.sha256)
        return h.hexdigest()

    @staticmethod
    def mask_email(email: str) -> str:
        """Masks email for display to unprivileged staff (e.g. j***n@example.com)."""
        if not email or "@" not in email:
            return "***"
        parts = email.split("@")
        name = parts[0]
        domain = parts[1]
        if len(name) <= 2:
            masked_name = name[0] + "*"
        else:
            masked_name = name[0] + "*" * (len(name) - 2) + name[-1]
        return f"{masked_name}@{domain}"

    @staticmethod
    def mask_phone(phone: str) -> str:
        """Masks phone number for privacy display (e.g. +1 ***-***-9921)."""
        if not phone or len(phone) < 4:
            return "***-****"
        return f"***-***-{phone[-4:]}"

# Singleton instance for platform-wide usage
pii_service = PIIEncryptionService()

