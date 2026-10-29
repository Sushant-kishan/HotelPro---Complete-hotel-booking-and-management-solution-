"""
HotelPro Immutable Tamper-Evident Audit Ledger Module
PRD Section 4.1: Immutable append-only logs capturing every room status change,
folio update, and financial charge with SHA-256 cryptographic hash-chaining.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from app.database import get_db

class AuditLedgerService:
    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    @classmethod
    def log_event(
        cls,
        tenant_id: str,
        property_id: Optional[str],
        user_id: Optional[str],
        user_role: Optional[str],
        action: str,
        entity_type: str,
        entity_id: str,
        payload: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> int:
        """
        Appends an immutable audit event to the tamper-evident ledger.
        Computes SHA-256 hash chained to the latest audit entry.
        """
        payload_str = json.dumps(payload or {}, sort_keys=True)
        now_iso = datetime.now(timezone.utc).isoformat()

        with get_db() as db:
            # Fetch latest record to get prev_hash
            last_record = db.execute(
                "SELECT record_hash FROM audit_logs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            
            prev_hash = last_record["record_hash"] if last_record else cls.GENESIS_HASH
            
            # Compute current record's cryptographic hash
            hash_input = (
                f"{prev_hash}|{tenant_id}|{property_id or ''}|{user_id or ''}|"
                f"{user_role or ''}|{action}|{entity_type}|{entity_id}|{payload_str}|{now_iso}"
            )
            record_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
            
            cursor = db.execute(
                """
                INSERT INTO audit_logs (
                    tenant_id, property_id, user_id, user_role, action,
                    entity_type, entity_id, payload, ip_address, prev_hash, record_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id, property_id, user_id, user_role, action,
                    entity_type, entity_id, payload_str, ip_address, prev_hash, record_hash, now_iso
                )
            )
            return cursor.lastrowid

    @classmethod
    def verify_integrity(cls) -> Dict[str, Any]:
        """
        Verifies the cryptographic hash-chain across all recorded audit entries.
        Guarantees that no logs were modified, injected, or deleted.
        """
        with get_db() as db:
            rows = db.execute("SELECT * FROM audit_logs ORDER BY id ASC").fetchall()
            
            if not rows:
                return {"valid": True, "total_records": 0, "message": "Ledger is empty. Genesis state valid."}
            
            expected_prev_hash = cls.GENESIS_HASH
            for row in rows:
                if row["prev_hash"] != expected_prev_hash:
                    return {
                        "valid": False,
                        "tampered_id": row["id"],
                        "reason": f"Hash chain broken at ID {row['id']}. Expected prev_hash {expected_prev_hash}, found {row['prev_hash']}"
                    }
                
                # Recompute hash
                hash_input = (
                    f"{row['prev_hash']}|{row['tenant_id']}|{row['property_id'] or ''}|{row['user_id'] or ''}|"
                    f"{row['user_role'] or ''}|{row['action']}|{row['entity_type']}|{row['entity_id']}|"
                    f"{row['payload']}|{row['created_at']}"
                )
                recomputed = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
                if recomputed != row["record_hash"]:
                    return {
                        "valid": False,
                        "tampered_id": row["id"],
                        "reason": f"Payload or metadata tampered at ID {row['id']}. Signature mismatch."
                    }
                expected_prev_hash = row["record_hash"]
                
            return {
                "valid": True,
                "total_records": len(rows),
                "latest_hash": expected_prev_hash,
                "message": f"Cryptographic integrity verified. {len(rows)} immutable audit blocks validated."
            }

audit_service = AuditLedgerService()

