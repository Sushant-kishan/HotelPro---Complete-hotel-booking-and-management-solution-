"""
HotelPro Room Inventory & Real-Time Availability Router
PRD Section 4.2: Dynamic Inventory Synchronization, Overbooking Control,
Real-time availability queries with p95 < 200ms latency.
"""
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException

from app.services.inventory_engine import inventory_engine
from app.database import get_db

router = APIRouter(prefix="/inventory", tags=["Room Inventory & Availability"])

@router.get("/availability")
def check_availability(
    property_id: str = Query(..., description="Target hotel property ID"),
    check_in_date: str = Query(..., description="Check-in date (YYYY-MM-DD)"),
    check_out_date: str = Query(..., description="Check-out date (YYYY-MM-DD)")
):
    """
    Real-time room availability and dynamic yield pricing query across all categories.
    Guarantees sub-second calculation across multi-day date spans.
    """
    try:
        results = inventory_engine.get_all_room_types_availability(
            property_id=property_id,
            check_in_date=check_in_date,
            check_out_date=check_out_date
        )
        return {
            "property_id": property_id,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "categories": results
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/rooms")
def get_all_rooms(property_id: str = Query(...)):
    """Returns all physical rooms for the property with operational and cleanliness status."""
    with get_db() as db:
        rows = db.execute(
            """
            SELECT r.*, rt.name as room_type_name, rt.code as room_type_code
            FROM rooms r
            JOIN room_types rt ON r.room_type_id = rt.id
            WHERE r.property_id = ?
            ORDER BY r.floor ASC, r.room_number ASC
            """,
            (property_id,)
        ).fetchall()
        return [dict(r) for r in rows]

@router.get("/properties")
def get_properties():
    """Lists properties configured under current tenant."""
    with get_db() as db:
        props = db.execute("SELECT * FROM properties ORDER BY name ASC").fetchall()
        return [dict(p) for p in props]

