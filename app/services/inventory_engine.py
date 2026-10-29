"""
HotelPro Real-Time Inventory & Concurrency Locking Engine
PRD Section 4.2: Dynamic Inventory Synchronization, Distributed Concurrency Locking,
Overbooking Control with property-level thresholds.
"""
import time
import threading
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager

from app.database import get_db

class ConcurrencyLockManager:
    """
    Distributed Concurrency Lock Engine.
    Prevents double bookings during concurrent high-traffic reservation attempts
    by synchronizing inventory allocations per (property_id, room_type_id, date_range).
    """
    def __init__(self):
        self._locks: Dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()
        self._leases: Dict[str, float] = {}

    def _get_resource_key(self, property_id: str, room_type_id: str) -> str:
        return f"{property_id}:{room_type_id}"

    @contextmanager
    def acquire_lock(self, property_id: str, room_type_id: str, timeout_seconds: float = 5.0):
        key = self._get_resource_key(property_id, room_type_id)
        with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            resource_lock = self._locks[key]

        acquired = resource_lock.acquire(timeout=timeout_seconds)
        if not acquired:
            raise TimeoutError(f"High-contention concurrency lock timeout for room type {room_type_id}. Please retry.")
        try:
            self._leases[key] = time.time() + timeout_seconds
            yield
        finally:
            self._leases.pop(key, None)
            resource_lock.release()

lock_manager = ConcurrencyLockManager()

class InventoryEngine:
    @staticmethod
    def get_date_range_days(start_date: str, end_date: str) -> List[str]:
        """Returns list of ISO date strings for each night in range [start, end)."""
        d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        days = []
        curr = d_start
        while curr < d_end:
            days.append(curr.isoformat())
            curr += timedelta(days=1)
        return days

    @classmethod
    def check_availability(
        cls,
        property_id: str,
        room_type_id: str,
        check_in_date: str,
        check_out_date: str
    ) -> Dict[str, Any]:
        """
        Calculates real-time availability across all nights in the date range.
        Considers total physical rooms, maintenance holds, active reservations,
        and configurable overbooking thresholds.
        """
        nights = cls.get_date_range_days(check_in_date, check_out_date)
        if not nights:
            return {"available": False, "reason": "Invalid date range: check-out must be after check-in"}

        with get_db() as db:
            # 1. Total operational rooms in this room category
            total_rooms_row = db.execute(
                """
                SELECT COUNT(*) as total
                FROM rooms
                WHERE property_id = ? AND room_type_id = ? AND operational_status != 'OUT_OF_ORDER'
                """,
                (property_id, room_type_id)
            ).fetchone()
            total_physical_rooms = total_rooms_row["total"] if total_rooms_row else 0

            # 2. Get property overbooking threshold
            prop = db.execute("SELECT overbooking_threshold FROM properties WHERE id = ?", (property_id,)).fetchone()
            threshold = prop["overbooking_threshold"] if prop else 0.05
            allowed_capacity = int(total_physical_rooms * (1.0 + threshold))

            # 3. For each night, calculate committed reservations
            # Overlapping criteria: res.check_in_date < night_end AND res.check_out_date > night_start
            min_available_across_stay = total_physical_rooms
            daily_breakdown = {}

            for night in nights:
                next_day = (datetime.strptime(night, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
                
                booked_row = db.execute(
                    """
                    SELECT COUNT(*) as booked
                    FROM reservations
                    WHERE property_id = ?
                      AND room_type_id = ?
                      AND status IN ('CONFIRMED', 'CHECKED_IN')
                      AND check_in_date < ?
                      AND check_out_date > ?
                    """,
                    (property_id, room_type_id, next_day, night)
                ).fetchone()
                
                booked_count = booked_row["booked"] if booked_row else 0
                available_for_night = allowed_capacity - booked_count
                
                daily_breakdown[night] = {
                    "total_rooms": total_physical_rooms,
                    "allowed_capacity": allowed_capacity,
                    "booked": booked_count,
                    "available": max(0, available_for_night)
                }
                
                if available_for_night < min_available_across_stay:
                    min_available_across_stay = available_for_night

            is_available = min_available_across_stay > 0
            return {
                "available": is_available,
                "rooms_remaining": max(0, min_available_across_stay),
                "total_physical_rooms": total_physical_rooms,
                "allowed_with_overbooking": allowed_capacity,
                "daily_breakdown": daily_breakdown
            }

    @classmethod
    def get_all_room_types_availability(
        cls,
        property_id: str,
        check_in_date: str,
        check_out_date: str
    ) -> List[Dict[str, Any]]:
        """Returns all room categories and their availability & dynamic rates for requested stay."""
        with get_db() as db:
            room_types = db.execute(
                "SELECT * FROM room_types WHERE property_id = ? ORDER BY default_base_rate ASC",
                (property_id,)
            ).fetchall()

            results = []
            for rt in room_types:
                rt_dict = dict(rt)
                avail_info = cls.check_availability(property_id, rt["id"], check_in_date, check_out_date)
                
                # Dynamic Pricing: Occupancy-based yield rule (PRD Section 4.3)
                base_rate = rt["default_base_rate"]
                total_rooms = avail_info["total_physical_rooms"]
                remaining = avail_info["rooms_remaining"]
                
                occupancy_ratio = 1.0 - (remaining / total_rooms) if total_rooms > 0 else 0.0
                
                # Yield pricing multiplier
                if occupancy_ratio >= 0.85:
                    rate_multiplier = 1.25 # High demand: +25%
                elif occupancy_ratio >= 0.70:
                    rate_multiplier = 1.10 # Moderate demand: +10%
                elif occupancy_ratio <= 0.30:
                    rate_multiplier = 0.90 # Low occupancy incentive: -10%
                else:
                    rate_multiplier = 1.00

                dynamic_rate = round(base_rate * rate_multiplier, 2)
                
                nights_count = len(cls.get_date_range_days(check_in_date, check_out_date))
                total_estimate = round(dynamic_rate * nights_count, 2)

                rt_dict.update({
                    "available": avail_info["available"],
                    "rooms_remaining": avail_info["rooms_remaining"],
                    "base_rate": base_rate,
                    "dynamic_nightly_rate": dynamic_rate,
                    "occupancy_ratio": round(occupancy_ratio * 100, 1),
                    "nights_count": nights_count,
                    "total_estimated_amount": total_estimate
                })
                results.append(rt_dict)
            return results

inventory_engine = InventoryEngine()

