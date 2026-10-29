"""
HotelPro Configuration Module
Handles environment settings, security keys, token lifetimes, and database configurations.
"""
import os
import secrets
from typing import Optional

class Settings:
    PROJECT_NAME: str = "HotelPro Enterprise Hotel Management Platform"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    # Security & Tokens
    # 15-minute inactivity termination strictly mandated by PRD Section 4.1
    SESSION_INACTIVITY_TIMEOUT_MINUTES: int = 15
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_SECRET_KEY: str = os.getenv("HOTELPRO_JWT_SECRET", "hotelpro-enterprise-super-secret-key-32b-min!!")
    JWT_ALGORITHM: str = "HS256"
    
    # Field-level AES-256 PII Encryption Key (32 bytes url-safe base64 or 32 raw bytes)
    # PRD Section 4.1: Field-level AES-256 encryption for guest PII
    AES_ENCRYPTION_KEY: bytes = os.getenv(
        "HOTELPRO_AES_KEY",
        "HotelProSecretAESKeyForPII32Bytes!".encode("utf-8")[:32]
    )
    
    # Blind index salt for deterministic hashed lookups on encrypted PII (email, phone)
    BLIND_INDEX_SALT: str = os.getenv("HOTELPRO_BLIND_SALT", "hotelpro-deterministic-salt-2026")
    
    # Multi-tenant Database
    DATABASE_PATH: str = os.getenv("HOTELPRO_DB_PATH", "hotelpro.db")
    
    # Overbooking Defaults (PRD Section 4.2)
    DEFAULT_OVERBOOKING_THRESHOLD_PERCENT: float = 0.05 # 5% default peak season buffer
    
    # Hardware Simulator Config
    KEYCARD_ENCODER_SYSTEM_ID: str = "ENC-HQ-FL1-DESK1"
    
settings = Settings()

