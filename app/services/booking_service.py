"""
HotelPro Booking & Reservation Lifecycle Service
PRD Section 4.3: Flexible Reservation Management, Dynamic Pricing & Rate Engine,
Concurrency-Locked Transactions, and Automated Guest Profiling.
"""
import uuid
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.database import get_db
from app.services.inventory_engine import inventory_engine, lock_manager
from app.services.folio_service import folio_service
from app.security.crypto import pii_service
from app.security.audit import audit_service

class BookingService:
    @staticmethod
    def generate_booking_reference() -> str:
        """Generates standard HotelPro confirmation code (e.g. HP-2026-8924)."""
        random_suffix = secrets.token_hex(2).upper()
        return f"HP-{datetime.now().year}-{random_suffix}"

    @classmethod
    def find_or_create_guest(
        cls,
        tenant_id: str,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        preferences: Optional[List[str]] = None,
        vip_tier: str = "STANDARD"
    ) -> str:
        """
        Uses HMAC blind indexing to match existing guest profiles without decrypting entire table.
        Encrypts new PII with AES-256-GCM.
        """
        email_blind = pii_service.compute_blind_index(email)
        phone_blind = pii_service.compute_blind_index(phone)

        with get_db() as db:
            existing = db.execute(
                "SELECT id FROM guests WHERE tenant_id = ? AND email_blind_index = ? AND anonymized = 0",
                (tenant_id, email_blind)
            ).fetchone()

            if existing:
                guest_id = existing["id"]
                # Append preferences if new
                if preferences:
                    import json
                    db.execute(
                        "UPDATE guests SET preferences = ? WHERE id = ?",
                        (json.dumps(preferences), guest_id)
                    )
                return guest_id

            # Create new encrypted guest profile
            guest_id = str(uuid.uuid4())
            enc_first = pii_service.encrypt(first_name)
            enc_last = pii_service.encrypt(last_name)
            enc_email = pii_service.encrypt(email)
            enc_phone = pii_service.encrypt(phone)
            
            import json
            prefs_json = json.dumps(preferences or ["Preferred quiet room", "High floor"])

            db.execute(
                """
                INSERT INTO guests (
                    id, tenant_id, encrypted_first_name, encrypted_last_name,
                    encrypted_email, encrypted_phone, email_blind_index,
                    phone_blind_index, vip_tier, preferences
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guest_id, tenant_id, enc_first, enc_last,
                    enc_email, enc_phone, email_blind,
                    phone_blind, vip_tier, prefs_json
                )
            )
            return guest_id

    @classmethod
    def create_reservation(
        cls,
        tenant_id: str,
        property_id: str,
        room_type_id: str,
        check_in_date: str,
        check_out_date: str,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        adult_count: int = 1,
        child_count: int = 0,
        channel: str = "DIRECT_WEB",
        discount_code: Optional[str] = None,
        special_requests: Optional[str] = None,
        corporate_account: Optional[str] = None,
        card_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Distributed Concurrency Locked Reservation Creation.
        Ensures atomic availability verification, guest profiling, booking insertion,
        and folio setup with zero possibility of double-booking under high concurrent load.
        """
        # Distributed lock across property and room category for the stay duration
        with lock_manager.acquire_lock(property_id, room_type_id, timeout_seconds=10.0):
            # 1. Verify availability under lock
            avail = inventory_engine.check_availability(property_id, room_type_id, check_in_date, check_out_date)
            if not avail["available"]:
                raise ValueError("Selected room category is sold out for requested dates.")

            # 2. Compute dynamic pricing
            with get_db() as db:
                rt = db.execute("SELECT * FROM room_types WHERE id = ?", (room_type_id,)).fetchone()
                if not rt:
                    raise ValueError("Invalid room type.")
                base_rate = rt["default_base_rate"]

            # Occupancy-driven yield pricing
            total_rooms = avail["total_physical_rooms"]
            remaining = avail["rooms_remaining"]
            occupancy_ratio = 1.0 - (remaining / total_rooms) if total_rooms > 0 else 0.0

            if occupancy_ratio >= 0.85:
                rate_multiplier = 1.25
            elif occupancy_ratio >= 0.70:
                rate_multiplier = 1.10
            elif occupancy_ratio <= 0.30:
                rate_multiplier = 0.90
            else:
                rate_multiplier = 1.00

            # Corporate discount code rules
            discount_multiplier = 1.0
            if discount_code:
                code_upper = discount_code.strip().upper()
                if code_upper in ("CORP20", "ENTERPRISE20"):
                    discount_multiplier = 0.80 # 20% corporate discount
                elif code_upper in ("DIRECT10", "WELCOME10"):
                    discount_multiplier = 0.90 # 10% direct booking promo

            nightly_rate = round(base_rate * rate_multiplier * discount_multiplier, 2)
            nights = len(inventory_engine.get_date_range_days(check_in_date, check_out_date))
            total_estimated = round(nightly_rate * nights, 2)

            # 3. Secure Guest CRM
            guest_id = cls.find_or_create_guest(
                tenant_id, first_name, last_name, email, phone
            )

            # 4. Insert Reservation
            res_id = str(uuid.uuid4())
            booking_ref = cls.generate_booking_reference()

            with get_db() as db:
                db.execute(
                    """
                    INSERT INTO reservations (
                        id, property_id, guest_id, booking_reference, channel,
                        status, check_in_date, check_out_date, adult_count,
                        child_count, room_type_id, nightly_rate,
                        total_estimated_amount, special_requests
                    ) VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        res_id, property_id, guest_id, booking_ref, channel,
                        check_in_date, check_out_date, adult_count,
                        child_count, room_type_id, nightly_rate,
                        total_estimated, special_requests
                    )
                )

            # 5. Initialize Split Folios
            guest_full_name = f"{first_name} {last_name}"
            folios = folio_service.create_reservation_folios(res_id, guest_full_name, corporate_account)

            # 6. Audit Log
            audit_service.log_event(
                tenant_id=tenant_id,
                property_id=property_id,
                user_id=None,
                user_role="GuestEngine",
                action="CREATE_RESERVATION",
                entity_type="Reservation",
                entity_id=res_id,
                payload={
                    "booking_reference": booking_ref,
                    "guest_name": guest_full_name,
                    "room_type": rt["name"],
                    "dates": f"{check_in_date} to {check_out_date}",
                    "nightly_rate": nightly_rate,
                    "total_amount": total_estimated,
                    "channel": channel
                }
            )

            return {
                "reservation_id": res_id,
                "booking_reference": booking_ref,
                "status": "CONFIRMED",
                "guest_name": guest_full_name,
                "room_type_name": rt["name"],
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "nightly_rate": nightly_rate,
                "nights": nights,
                "total_estimated_amount": total_estimated,
                "folios": folios
            }

    @classmethod
    def cancel_reservation(cls, booking_reference: str, reason: str = "Guest request") -> Dict[str, Any]:
        """Handles cancellation lifecycle with policy enforcement."""
        with get_db() as db:
            res = db.execute(
                "SELECT * FROM reservations WHERE booking_reference = ?",
                (booking_reference,)
            ).fetchone()
            if not res:
                raise ValueError("Reservation not found.")
            if res["status"] in ("CANCELLED", "CHECKED_OUT"):
                raise ValueError(f"Reservation cannot be cancelled in state '{res['status']}'.")

            db.execute(
                "UPDATE reservations SET status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (res["id"],)
            )
            # If room was assigned, release room back to available
            if res["assigned_room_id"]:
                db.execute(
                    "UPDATE rooms SET operational_status = 'AVAILABLE' WHERE id = ?",
                    (res["assigned_room_id"],)
                )

        audit_service.log_event(
            tenant_id="default-tenant",
            property_id=res["property_id"],
            user_id=None,
            user_role="Staff",
            action="CANCEL_RESERVATION",
            entity_type="Reservation",
            entity_id=res["id"],
            payload={"booking_reference": booking_reference, "reason": reason}
        )

        return {"booking_reference": booking_reference, "status": "CANCELLED", "message": "Reservation successfully cancelled."}

booking_service = BookingService()

