"""
HotelPro Multi-Tenant Database Layer
High-concurrency SQLite persistence with WAL mode, foreign keys, row factories,
and automatic schema migration/initialization.
"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Generator
from app.config import settings

_local = threading.local()

def get_connection() -> sqlite3.Connection:
    """Returns a thread-local SQLite database connection configured with WAL and FKs."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(
            settings.DATABASE_PATH,
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging for high concurrency and foreign key constraints
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        _local.conn = conn
    return _local.conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def init_db():
    """Initializes multi-tenant tables, indexes, and constraints per PRD specifications."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Tenants & Properties
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        tier TEXT NOT NULL DEFAULT 'ENTERPRISE',
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS properties (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        name TEXT NOT NULL,
        code TEXT NOT NULL UNIQUE,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        currency TEXT NOT NULL DEFAULT 'USD',
        address TEXT NOT NULL,
        overbooking_threshold REAL NOT NULL DEFAULT 0.05,
        current_business_date TEXT NOT NULL DEFAULT (DATE('now')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
    );
    """)

    # 2. Staff Users & RBAC (PRD Section 4.1)
    # Roles: SuperAdmin, PropertyManager, FrontDesk, Housekeeping, Auditor
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        property_id TEXT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        totp_secret TEXT,
        totp_enabled INTEGER NOT NULL DEFAULT 0,
        backup_codes TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        last_login TIMESTAMP,
        last_activity TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
        FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE SET NULL
    );
    """)

    # 3. Room Types & Physical Rooms (PRD Section 4.2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS room_types (
        id TEXT PRIMARY KEY,
        property_id TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        base_occupancy INTEGER NOT NULL DEFAULT 2,
        max_occupancy INTEGER NOT NULL DEFAULT 4,
        default_base_rate REAL NOT NULL,
        amenities TEXT, -- JSON array
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
        UNIQUE (property_id, code)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY,
        property_id TEXT NOT NULL,
        room_type_id TEXT NOT NULL,
        room_number TEXT NOT NULL,
        floor INTEGER NOT NULL DEFAULT 1,
        operational_status TEXT NOT NULL DEFAULT 'AVAILABLE', -- AVAILABLE, MAINTENANCE, OUT_OF_ORDER
        housekeeping_status TEXT NOT NULL DEFAULT 'CLEAN', -- CLEAN, INSPECTED, DIRTY, IN_PROGRESS
        active_keycard_token TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
        FOREIGN KEY (room_type_id) REFERENCES room_types(id) ON DELETE CASCADE,
        UNIQUE (property_id, room_number)
    );
    """)

    # 4. Guest Profiles with AES-256 Field Encryption & Blind Indexing (PRD Section 4.1, 4.4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guests (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        encrypted_first_name TEXT NOT NULL,
        encrypted_last_name TEXT NOT NULL,
        encrypted_email TEXT NOT NULL,
        encrypted_phone TEXT NOT NULL,
        encrypted_id_document TEXT,
        email_blind_index TEXT NOT NULL,
        phone_blind_index TEXT NOT NULL,
        vip_tier TEXT NOT NULL DEFAULT 'STANDARD', -- STANDARD, SILVER, GOLD, PLATINUM
        preferences TEXT, -- JSON array of notes
        anonymized INTEGER NOT NULL DEFAULT 0, -- GDPR right-to-erasure marker
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_guest_email_blind ON guests(email_blind_index);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_guest_phone_blind ON guests(phone_blind_index);")

    # 5. Reservations & Bookings (PRD Section 4.3)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id TEXT PRIMARY KEY,
        property_id TEXT NOT NULL,
        guest_id TEXT NOT NULL,
        booking_reference TEXT NOT NULL UNIQUE,
        channel TEXT NOT NULL DEFAULT 'DIRECT_WEB', -- DIRECT_WEB, BOOKING_COM, EXPEDIA, WALK_IN, CORPORATE
        status TEXT NOT NULL DEFAULT 'CONFIRMED', -- CONFIRMED, CHECKED_IN, CHECKED_OUT, CANCELLED, NO_SHOW
        check_in_date TEXT NOT NULL,
        check_out_date TEXT NOT NULL,
        adult_count INTEGER NOT NULL DEFAULT 1,
        child_count INTEGER NOT NULL DEFAULT 0,
        room_type_id TEXT NOT NULL,
        assigned_room_id TEXT,
        nightly_rate REAL NOT NULL,
        total_estimated_amount REAL NOT NULL,
        special_requests TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
        FOREIGN KEY (guest_id) REFERENCES guests(id) ON DELETE CASCADE,
        FOREIGN KEY (room_type_id) REFERENCES room_types(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_room_id) REFERENCES rooms(id) ON DELETE SET NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_dates ON reservations(property_id, check_in_date, check_out_date, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_res_ref ON reservations(booking_reference);")

    # 6. Folios & Split Billing (PRD Section 4.4, 4.5)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folios (
        id TEXT PRIMARY KEY,
        reservation_id TEXT NOT NULL,
        folio_type TEXT NOT NULL DEFAULT 'MASTER', -- MASTER (Room & Tax), INCIDENTAL (F&B, Minibar)
        payer_name TEXT NOT NULL,
        payer_type TEXT NOT NULL DEFAULT 'GUEST', -- GUEST, CORPORATE, OTA
        status TEXT NOT NULL DEFAULT 'OPEN', -- OPEN, CLOSED, SETTLED
        total_charges REAL NOT NULL DEFAULT 0.0,
        total_payments REAL NOT NULL DEFAULT 0.0,
        balance REAL NOT NULL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reservation_id) REFERENCES reservations(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folio_items (
        id TEXT PRIMARY KEY,
        folio_id TEXT NOT NULL,
        category TEXT NOT NULL, -- ROOM_CHARGE, TAX, RESTAURANT, MINIBAR, ROOM_SERVICE, SPA, PARKING
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        tax_amount REAL NOT NULL DEFAULT 0.0,
        posted_by_user_id TEXT,
        posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (folio_id) REFERENCES folios(id) ON DELETE CASCADE
    );
    """)

    # 7. Payment Transactions & Pre-Authorizations (PRD Section 4.5)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_transactions (
        id TEXT PRIMARY KEY,
        folio_id TEXT NOT NULL,
        transaction_type TEXT NOT NULL, -- PRE_AUTH, CAPTURE, REFUND, VOID
        amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        gateway_token TEXT NOT NULL,
        card_brand TEXT NOT NULL,
        card_last4 TEXT NOT NULL,
        auth_code TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'SUCCESS', -- SUCCESS, FAILED, PENDING
        gateway_response TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (folio_id) REFERENCES folios(id) ON DELETE CASCADE
    );
    """)

    # 8. Housekeeping Tasks & Governance (PRD Section 4.4)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS housekeeping_tasks (
        id TEXT PRIMARY KEY,
        property_id TEXT NOT NULL,
        room_id TEXT NOT NULL,
        assigned_user_id TEXT,
        task_type TEXT NOT NULL DEFAULT 'DEPARTURE_CLEAN', -- DEPARTURE_CLEAN, STAYOVER_SERVICE, DEEP_CLEAN, INSPECTION
        priority TEXT NOT NULL DEFAULT 'NORMAL', -- HIGH, NORMAL, LOW
        status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, COMPLETED, INSPECTED
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
        FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)

    # 9. Tamper-Evident Immutable Append-Only Audit Ledger (PRD Section 4.1)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT NOT NULL,
        property_id TEXT,
        user_id TEXT,
        user_role TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload TEXT, -- JSON representation
        ip_address TEXT,
        prev_hash TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);")

    # 10. Night Audit EOD Journal Logs (PRD Section 4.4, 6)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS night_audit_records (
        id TEXT PRIMARY KEY,
        property_id TEXT NOT NULL,
        business_date TEXT NOT NULL,
        auditor_user_id TEXT NOT NULL,
        total_rooms_occupied INTEGER NOT NULL,
        occupancy_rate REAL NOT NULL,
        total_room_revenue REAL NOT NULL,
        total_tax_revenue REAL NOT NULL,
        total_incidental_revenue REAL NOT NULL,
        total_payments_collected REAL NOT NULL,
        erp_sync_status TEXT NOT NULL DEFAULT 'PENDING',
        erp_journal_payload TEXT,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
        FOREIGN KEY (auditor_user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()

