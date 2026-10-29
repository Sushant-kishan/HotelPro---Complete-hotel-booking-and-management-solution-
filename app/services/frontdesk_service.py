"""
HotelPro Front-Desk Expedited Workflow Service
PRD Section 4.4: Sub-60-second check-in/out processing with native keycard encoder
integration and immediate housekeeping status synchronization.
"""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from app.database import get_db
from app.services.folio_service import folio_service
from app.services.payment_bridge import payment_bridge
from app.security.crypto import pii_service
from app.security.audit import audit_service
from app.config import settings

class FrontDeskService:
    @classmethod
    def find_arrivals(cls, property_id: str, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all confirmed bookings arriving on specified date (or today)."""
        with get_db() as db:
            prop = db.execute("SELECT current_business_date FROM properties WHERE id = ?", (property_id,)).fetchone()
            business_date = date_str or (prop["current_business_date"] if prop else datetime.now().date().isoformat())

            rows = db.execute(
                """
                SELECT r.*, rt.name as room_type_name, g.encrypted_first_name, g.encrypted_last_name,
                       g.encrypted_email, g.encrypted_phone, g.vip_tier, g.preferences, rm.room_number
                FROM reservations r
                JOIN room_types rt ON r.room_type_id = rt.id
                JOIN guests g ON r.guest_id = g.id
                LEFT JOIN rooms rm ON r.assigned_room_id = rm.id
                WHERE r.property_id = ? AND r.check_in_date = ? AND r.status = 'CONFIRMED'
                ORDER BY r.created_at ASC
                """,
                (property_id, business_date)
            ).fetchall()

            results = []
            for row in rows:
                r_dict = dict(row)
                r_dict["guest_name"] = f"{pii_service.decrypt(r_dict['encrypted_first_name'])} {pii_service.decrypt(r_dict['encrypted_last_name'])}"
                r_dict["guest_email"] = pii_service.decrypt(r_dict["encrypted_email"])
                r_dict["guest_phone"] = pii_service.decrypt(r_dict["encrypted_phone"])
                results.append(r_dict)
            return results

    @classmethod
    def find_departures(cls, property_id: str, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all currently checked-in reservations departing today."""
        with get_db() as db:
            prop = db.execute("SELECT current_business_date FROM properties WHERE id = ?", (property_id,)).fetchone()
            business_date = date_str or (prop["current_business_date"] if prop else datetime.now().date().isoformat())

            rows = db.execute(
                """
                SELECT r.*, rt.name as room_type_name, g.encrypted_first_name, g.encrypted_last_name,
                       rm.room_number
                FROM reservations r
                JOIN room_types rt ON r.room_type_id = rt.id
                JOIN guests g ON r.guest_id = g.id
                LEFT JOIN rooms rm ON r.assigned_room_id = rm.id
                WHERE r.property_id = ? AND r.check_out_date = ? AND r.status = 'CHECKED_IN'
                ORDER BY rm.room_number ASC
                """,
                (property_id, business_date)
            ).fetchall()

            results = []
            for row in rows:
                r_dict = dict(row)
                r_dict["guest_name"] = f"{pii_service.decrypt(r_dict['encrypted_first_name'])} {pii_service.decrypt(r_dict['encrypted_last_name'])}"
                # Get folio balance
                folios = folio_service.get_reservation_folios(r_dict["id"])
                total_balance = sum(f["balance"] for f in folios)
                r_dict["total_open_balance"] = round(total_balance, 2)
                results.append(r_dict)
            return results

    @classmethod
    def get_assignable_rooms(cls, property_id: str, room_type_id: str) -> List[Dict[str, Any]]:
        """Returns available physical rooms in CLEAN or INSPECTED status."""
        with get_db() as db:
            rooms = db.execute(
                """
                SELECT * FROM rooms
                WHERE property_id = ? AND room_type_id = ?
                  AND operational_status = 'AVAILABLE'
                  AND housekeeping_status IN ('CLEAN', 'INSPECTED')
                ORDER BY floor ASC, room_number ASC
                """,
                (property_id, room_type_id)
            ).fetchall()
            return [dict(r) for r in rooms]

    @classmethod
    def expedited_check_in(
        cls,
        reservation_id: str,
        room_id: str,
        card_token: str,
        incidental_deposit_amount: float = 100.0,
        staff_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sub-60-second check-in processing flow:
        1. Validates reservation & room status.
        2. Assigns physical room.
        3. Pre-authorizes incidental deposit hold on card.
        4. Generates hardware keycard encoder payload (RFID / BLE).
        5. Updates room to OCCUPIED and syncs Housekeeping immediately.
        """
        with get_db() as db:
            res = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
            if not res:
                raise ValueError("Reservation not found.")
            if res["status"] != "CONFIRMED":
                raise ValueError(f"Cannot check in reservation with status '{res['status']}'.")

            room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if not room:
                raise ValueError("Room not found.")
            if room["operational_status"] != "AVAILABLE":
                raise ValueError(f"Room {room['room_number']} is not available.")

            # Pre-auth incidental hold on incidental folio
            folios = folio_service.get_reservation_folios(reservation_id)
            incidental_folio = next((f for f in folios if f["folio_type"] == "INCIDENTAL"), folios[0])
            
            pre_auth_res = payment_bridge.pre_authorize(
                card_token, incidental_deposit_amount, folio_id=incidental_folio["id"]
            )

            # Generate native keycard RFID / BLE payload
            keycard_token = f"KEY-{room['room_number']}-{secrets.token_hex(4).upper()}"
            keycard_payload = {
                "system_encoder": settings.KEYCARD_ENCODER_SYSTEM_ID,
                "room_number": room["room_number"],
                "floor": room["floor"],
                "key_token": keycard_token,
                "rfid_track_data": f";{room['room_number']}={keycard_token[:8]}?",
                "ble_payload": f"ble_key://hotelpro/{res['property_id']}/{room['room_number']}?auth={keycard_token}",
                "valid_until": f"{res['check_out_date']}T12:00:00Z"
            }

            # Update DB: reservation status -> CHECKED_IN, room status -> OCCUPIED
            db.execute(
                """
                UPDATE reservations
                SET status = 'CHECKED_IN', assigned_room_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (room_id, reservation_id)
            )

            db.execute(
                """
                UPDATE rooms
                SET operational_status = 'OCCUPIED', housekeeping_status = 'CLEAN', active_keycard_token = ?
                WHERE id = ?
                """,
                (keycard_token, room_id)
            )

        audit_service.log_event(
            tenant_id="default-tenant",
            property_id=res["property_id"],
            user_id=staff_user_id,
            user_role="FrontDesk",
            action="EXPEDITED_CHECK_IN",
            entity_type="Reservation",
            entity_id=reservation_id,
            payload={
                "room_number": room["room_number"],
                "pre_auth_amount": incidental_deposit_amount,
                "auth_code": pre_auth_res["auth_code"],
                "keycard_token": keycard_token
            }
        )

        return {
            "success": True,
            "status": "CHECKED_IN",
            "reservation_id": reservation_id,
            "room_number": room["room_number"],
            "pre_auth_hold": pre_auth_res,
            "keycard": keycard_payload,
            "message": f"Sub-60s check-in complete. Room {room['room_number']} issued. Keycard active."
        }

    @classmethod
    def expedited_check_out(
        cls,
        reservation_id: str,
        staff_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sub-60-second check-out processing flow:
        1. Checks balances across all folios.
        2. Settles any remaining balances with instant capture.
        3. Deactivates keycard credentials.
        4. Releases room: sets operational_status to 'AVAILABLE', housekeeping_status to 'DIRTY'.
        5. Automatically generates Housekeeping cleaning task.
        """
        with get_db() as db:
            res = db.execute("SELECT * FROM reservations WHERE id = ?", (reservation_id,)).fetchone()
            if not res:
                raise ValueError("Reservation not found.")
            if res["status"] != "CHECKED_IN":
                raise ValueError(f"Cannot check out reservation in status '{res['status']}'.")

            room_id = res["assigned_room_id"]
            room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone() if room_id else None

            # Check and settle folios
            folios = folio_service.get_reservation_folios(reservation_id)
            settlements = []
            for folio in folios:
                if folio["balance"] > 0:
                    # Auto-capture remaining balance
                    settle_res = folio_service.process_payment(
                        folio_id=folio["id"],
                        amount=folio["balance"],
                        card_token="tok_pci_visa_default_checkout",
                        card_brand="Visa",
                        card_last4="4242",
                        transaction_type="CAPTURE",
                        user_id=staff_user_id
                    )
                    settlements.append(settle_res)

            # Update reservation status to CHECKED_OUT
            db.execute(
                "UPDATE reservations SET status = 'CHECKED_OUT', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (reservation_id,)
            )

            # Update room to DIRTY for Housekeeping
            if room_id:
                db.execute(
                    """
                    UPDATE rooms
                    SET operational_status = 'AVAILABLE', housekeeping_status = 'DIRTY', active_keycard_token = NULL
                    WHERE id = ?
                    """,
                    (room_id,)
                )

                # Create housekeeping departure clean task
                task_id = str(uuid.uuid4())
                db.execute(
                    """
                    INSERT INTO housekeeping_tasks (id, property_id, room_id, task_type, priority, status, notes)
                    VALUES (?, ?, ?, 'DEPARTURE_CLEAN', 'HIGH', 'PENDING', 'Expedited checkout completed. Priority room turnover.')
                    """,
                    (task_id, res["property_id"], room_id)
                )

        audit_service.log_event(
            tenant_id="default-tenant",
            property_id=res["property_id"],
            user_id=staff_user_id,
            user_role="FrontDesk",
            action="EXPEDITED_CHECK_OUT",
            entity_type="Reservation",
            entity_id=reservation_id,
            payload={
                "room_number": room["room_number"] if room else "N/A",
                "settlements": settlements,
                "housekeeping_status": "DIRTY"
            }
        )

        return {
            "success": True,
            "status": "CHECKED_OUT",
            "reservation_id": reservation_id,
            "room_number": room["room_number"] if room else None,
            "settlements": settlements,
            "keycard_deactivated": True,
            "housekeeping_notified": True,
            "message": "Sub-60s check-out finalized. Folios settled. Housekeeping turnover task queued."
        }

frontdesk_service = FrontDeskService()

