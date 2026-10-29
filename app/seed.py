"""
HotelPro Database Seeding Script
Initializes sample property, room categories, physical rooms, staff user accounts
with predefined roles and credentials, and active reservations.
"""
import uuid
import json
from datetime import datetime, timedelta
from app.database import get_db, init_db
from app.security.auth import hash_password
from app.security.crypto import pii_service
from app.security.audit import audit_service
from app.services.booking_service import booking_service
from app.services.folio_service import folio_service

def seed_demo_data():
    init_db()
    
    with get_db() as db:
        # Check if already seeded
        existing_tenant = db.execute("SELECT id FROM tenants LIMIT 1").fetchone()
        if existing_tenant:
            return

        print("Seeding initial enterprise hotel demo data...")

        # 1. Tenant
        tenant_id = "tenant-horizon-global"
        db.execute(
            "INSERT INTO tenants (id, name, tier, status) VALUES (?, ?, 'ENTERPRISE', 'ACTIVE')",
            (tenant_id, "Grand Horizon Hospitality Group")
        )

        # 2. Property
        property_id = "prop-horizon-miami"
        today_str = datetime.now().date().isoformat()
        db.execute(
            """
            INSERT INTO properties (id, tenant_id, name, code, timezone, currency, address, overbooking_threshold, current_business_date)
            VALUES (?, ?, ?, 'GH-MIA', 'America/New_York', 'USD', '1000 Ocean Drive, Miami Beach, FL 33139', 0.05, ?)
            """,
            (property_id, tenant_id, "Grand Horizon Resort & Spa, Miami", today_str)
        )

        # 3. Staff Users for all 5 RBAC roles (PRD Section 4.1)
        # Standard TOTP test secret: JBSWY3DPEHPK3PXP
        totp_secret = "JBSWY3DPEHPK3PXP"
        backup_codes = json.dumps(["A1B2-C3D4", "E5F6-G7H8", "J9K0-L1M2"])

        users = [
            ("user-admin", "admin", "admin@hotelpro.internal", "Alex Vance (Super Admin)", "SuperAdmin", "admin123", 1),
            ("user-manager", "manager", "manager@hotelpro.internal", "Elena Rostova (General Manager)", "PropertyManager", "manager123", 1),
            ("user-frontdesk", "frontdesk", "frontdesk@hotelpro.internal", "Marcus Chen (Front Desk Lead)", "FrontDesk", "frontdesk123", 1),
            ("user-housekeeper", "housekeeper", "housekeeping@hotelpro.internal", "Rosa Morales (Housekeeping)", "Housekeeping", "clean123", 0),
            ("user-auditor", "auditor", "auditor@hotelpro.internal", "David Sterling (Night Auditor)", "Auditor", "audit123", 1),
        ]

        for u_id, uname, email, name, role, pwd, mfa_en in users:
            pwd_hash = hash_password(pwd)
            db.execute(
                """
                INSERT INTO users (id, tenant_id, property_id, username, email, password_hash, full_name, role, totp_secret, totp_enabled, backup_codes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (u_id, tenant_id, property_id, uname, email, pwd_hash, name, role, totp_secret, mfa_en, backup_codes)
            )

        # 4. Room Types
        room_types = [
            ("rt-deluxe-king", "DLX-KNG", "Deluxe Ocean King", "Spacious 450 sq.ft room with king bed and ocean balcony.", 2, 3, 240.0, ["King Bed", "Ocean View", "Balcony", "Free WiFi", "Rain Shower"]),
            ("rt-exec-suite", "EXEC-STE", "Executive Oceanfront Suite", "Luxury 750 sq.ft suite with private lounge and whirlpool bath.", 2, 4, 480.0, ["King Bed", "Living Room", "Whirlpool", "Espresso Bar", "Butler Service"]),
            ("rt-penthouse", "PRES-VIL", "Presidential Sky Villa", "Top-floor penthouse with private infinity plunge pool and 360 panoramic views.", 4, 6, 1250.0, ["2 Master Suites", "Private Pool", "Chef Kitchen", "Chauffeur"]),
            ("rt-std-queen", "STD-DBL", "Standard Double Queen", "Comfortable 380 sq.ft room with two queen beds.", 2, 4, 190.0, ["2 Queen Beds", "Smart TV", "Mini Fridge", "Work Desk"]),
        ]

        for rt_id, code, name, desc, base_occ, max_occ, rate, amenities in room_types:
            db.execute(
                """
                INSERT INTO room_types (id, property_id, code, name, description, base_occupancy, max_occupancy, default_base_rate, amenities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rt_id, property_id, code, name, desc, base_occ, max_occ, rate, json.dumps(amenities))
            )

        # 5. Physical Rooms
        rooms = [
            ("rm-101", "rt-std-queen", "101", 1, "AVAILABLE", "CLEAN"),
            ("rm-102", "rt-std-queen", "102", 1, "AVAILABLE", "INSPECTED"),
            ("rm-103", "rt-deluxe-king", "103", 1, "AVAILABLE", "CLEAN"),
            ("rm-201", "rt-deluxe-king", "201", 2, "OCCUPIED", "CLEAN"),
            ("rm-202", "rt-deluxe-king", "202", 2, "AVAILABLE", "DIRTY"),
            ("rm-203", "rt-exec-suite", "203", 2, "AVAILABLE", "INSPECTED"),
            ("rm-301", "rt-exec-suite", "301", 3, "AVAILABLE", "CLEAN"),
            ("rm-302", "rt-exec-suite", "302", 3, "OUT_OF_ORDER", "OUT_OF_ORDER"),
            ("rm-401", "rt-penthouse", "401", 4, "AVAILABLE", "INSPECTED"),
        ]

        for r_id, rt_id, num, fl, op_stat, hk_stat in rooms:
            db.execute(
                """
                INSERT INTO rooms (id, property_id, room_type_id, room_number, floor, operational_status, housekeeping_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (r_id, property_id, rt_id, num, fl, op_stat, hk_stat)
            )

        print("Seeding sample guest reservations and folios...")

    # 6. Create active reservations using standard booking service
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    three_days = (datetime.now().date() + timedelta(days=3)).isoformat()
    five_days = (datetime.now().date() + timedelta(days=5)).isoformat()

    # Reservation 1: Arriving Today (for testing Sub-60s Check-In)
    res1 = booking_service.create_reservation(
        tenant_id=tenant_id,
        property_id=property_id,
        room_type_id="rt-deluxe-king",
        check_in_date=today_str,
        check_out_date=three_days,
        first_name="Sophia",
        last_name="Rodriguez",
        email="sophia.rodriguez@example.com",
        phone="+1 305-555-8123",
        special_requests="Prefers high floor and extra pillows",
        channel="DIRECT_WEB"
    )

    # Reservation 2: In-House Stays (for testing Room service charges, Split folios & Check-Out)
    res2 = booking_service.create_reservation(
        tenant_id=tenant_id,
        property_id=property_id,
        room_type_id="rt-deluxe-king",
        check_in_date=today_str,
        check_out_date=tomorrow,
        first_name="Julian",
        last_name="Mercer",
        email="julian.mercer@corporate-tech.com",
        phone="+1 415-555-0982",
        channel="CORPORATE",
        corporate_account="TechCorp Global Inc."
    )

    # Put res2 in CHECKED_IN state assigned to room 201
    with get_db() as db:
        db.execute(
            """
            UPDATE reservations
            SET status = 'CHECKED_IN', assigned_room_id = 'rm-201'
            WHERE id = ?
            """,
            (res2["reservation_id"],)
        )
        db.execute(
            "UPDATE rooms SET operational_status = 'OCCUPIED', active_keycard_token = 'KEY-201-9B3F' WHERE id = 'rm-201'"
        )

    # Post sample incidental charges on res2 folios
    folios = folio_service.get_reservation_folios(res2["reservation_id"])
    incidental_folio = next((f for f in folios if f["folio_type"] == "INCIDENTAL"), folios[0])
    master_folio = next((f for f in folios if f["folio_type"] == "MASTER"), folios[0])

    folio_service.post_charge(
        folio_id=incidental_folio["id"],
        category="RESTAURANT",
        description="Ocean Terrace Fine Dining - Dinner for 2",
        amount=145.00,
        tax_rate=0.08,
        posted_by_user_id="user-frontdesk"
    )
    folio_service.post_charge(
        folio_id=incidental_folio["id"],
        category="MINIBAR",
        description="Premium Sparkling Water & Snacks",
        amount=28.00,
        tax_rate=0.08,
        posted_by_user_id="user-frontdesk"
    )

    print("Demo data successfully seeded!")

if __name__ == "__main__":
    seed_demo_data()

