"""
HotelPro Housekeeping Operations & Task Governance Service
PRD Section 4.4: Real-time housekeeping status synchronization, task distribution,
and room turnover management.
"""
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.database import get_db
from app.security.audit import audit_service

class HousekeepingService:
    VALID_STATUSES = {"DIRTY", "IN_PROGRESS", "CLEAN", "INSPECTED", "OUT_OF_ORDER"}

    @classmethod
    def get_room_board(cls, property_id: str) -> List[Dict[str, Any]]:
        """Returns real-time status of all rooms for the housekeeping dashboard."""
        with get_db() as db:
            rows = db.execute(
                """
                SELECT r.id, r.room_number, r.floor, r.operational_status, r.housekeeping_status,
                       rt.name as room_type_name,
                       ht.id as active_task_id, ht.task_type, ht.priority, ht.status as task_status,
                       u.full_name as assigned_housekeeper
                FROM rooms r
                JOIN room_types rt ON r.room_type_id = rt.id
                LEFT JOIN housekeeping_tasks ht ON r.id = ht.room_id AND ht.status != 'COMPLETED'
                LEFT JOIN users u ON ht.assigned_user_id = u.id
                WHERE r.property_id = ?
                ORDER BY r.floor ASC, r.room_number ASC
                """,
                (property_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    @classmethod
    def update_room_status(
        cls,
        room_id: str,
        new_status: str,
        staff_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Updates housekeeping cleanliness status (CLEAN, INSPECTED, DIRTY, IN_PROGRESS, OUT_OF_ORDER).
        Synchronizes operational status and logs audit entry.
        """
        clean_status = new_status.upper().strip()
        if clean_status not in cls.VALID_STATUSES:
            raise ValueError(f"Invalid housekeeping status '{new_status}'. Valid values: {cls.VALID_STATUSES}")

        with get_db() as db:
            room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if not room:
                raise ValueError("Room not found.")

            # Operational status mapping
            operational_status = "OUT_OF_ORDER" if clean_status == "OUT_OF_ORDER" else room["operational_status"]
            if room["operational_status"] == "OUT_OF_ORDER" and clean_status != "OUT_OF_ORDER":
                operational_status = "AVAILABLE"

            db.execute(
                """
                UPDATE rooms
                SET housekeeping_status = ?, operational_status = ?
                WHERE id = ?
                """,
                (clean_status, operational_status, room_id)
            )

            # If marked INSPECTED or CLEAN, complete any active tasks
            if clean_status in ("CLEAN", "INSPECTED"):
                db.execute(
                    """
                    UPDATE housekeeping_tasks
                    SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
                    WHERE room_id = ? AND status != 'COMPLETED'
                    """,
                    (room_id,)
                )

        audit_service.log_event(
            tenant_id="default-tenant",
            property_id=room["property_id"],
            user_id=staff_user_id,
            user_role="Housekeeping",
            action="UPDATE_ROOM_CLEANLINESS",
            entity_type="Room",
            entity_id=room_id,
            payload={
                "room_number": room["room_number"],
                "old_status": room["housekeeping_status"],
                "new_status": clean_status
            }
        )

        return {
            "room_id": room_id,
            "room_number": room["room_number"],
            "housekeeping_status": clean_status,
            "operational_status": operational_status,
            "message": f"Room {room['room_number']} status updated to {clean_status}."
        }

housekeeping_service = HousekeepingService()

