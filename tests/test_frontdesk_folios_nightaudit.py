"""
Automated Test Suite for Expedited Front Desk (<60s Flow), Multi-Payer Split Folios,
PCI-DSS Tokenized Capture, Single-Click Night Audit, and Cryptographic Audit Chain.
PRD Sections 4.1, 4.4, 4.5, 6
"""
import pytest
from datetime import datetime, timedelta

from app.database import get_db
from app.services.booking_service import booking_service
from app.services.frontdesk_service import frontdesk_service
from app.services.folio_service import folio_service
from app.services.night_audit_service import night_audit_service
from app.services.erp_sync import erp_bridge
from app.security.audit import audit_service
from app.security.crypto import pii_service

def test_aes256_pii_encryption_and_blind_indexing():
    email = "vip.guest@luxurytravel.com"
    phone = "+1 305-998-1234"

    encrypted_email = pii_service.encrypt(email)
    assert encrypted_email != email
    decrypted_email = pii_service.decrypt(encrypted_email)
    assert decrypted_email == email

    # Blind index is deterministic
    blind1 = pii_service.compute_blind_index(email)
    blind2 = pii_service.compute_blind_index(email)
    assert blind1 == blind2
    assert len(blind1) == 64 # SHA-256 hex string

    # Masking for privacy
    assert pii_service.mask_email(email) == "v*******t@luxurytravel.com"
    assert pii_service.mask_phone(phone) == "***-***-1234"

def test_expedited_sub_60s_check_in_and_keycard_generation():
    # Pick dates and create reservation
    check_in = "2027-05-01"
    check_out = "2027-05-04"

    res = booking_service.create_reservation(
        tenant_id="tenant-horizon-global",
        property_id="prop-horizon-miami",
        room_type_id="rt-std-queen",
        check_in_date=check_in,
        check_out_date=check_out,
        first_name="Alexander",
        last_name="Wright",
        email="alex.wright@test.com",
        phone="+1 555-888-9999"
    )

    # Get assignable room dynamically
    assignable_rooms = frontdesk_service.get_assignable_rooms("prop-horizon-miami", "rt-std-queen")
    assert len(assignable_rooms) > 0
    assigned_room = assignable_rooms[0]

    # Sub-60s Expedited Check-In
    checkin_res = frontdesk_service.expedited_check_in(
        reservation_id=res["reservation_id"],
        room_id=assigned_room["id"],
        card_token="tok_pci_visa_test_token",
        incidental_deposit_amount=150.0,
        staff_user_id="user-frontdesk"
    )

    assert checkin_res["success"] is True
    assert checkin_res["status"] == "CHECKED_IN"
    assert checkin_res["room_number"] == assigned_room["room_number"]
    assert "pre_auth_hold" in checkin_res
    assert checkin_res["pre_auth_hold"]["amount"] == 150.0

    # Keycard encoder verification
    keycard = checkin_res["keycard"]
    assert f"KEY-{assigned_room['room_number']}-" in keycard["key_token"]
    assert "ble_key://" in keycard["ble_payload"]

def test_multi_payer_split_folio_and_incidental_posting():
    check_in = "2027-06-10"
    check_out = "2027-06-12"

    # Create corporate reservation with split folios
    res = booking_service.create_reservation(
        tenant_id="tenant-horizon-global",
        property_id="prop-horizon-miami",
        room_type_id="rt-deluxe-king",
        check_in_date=check_in,
        check_out_date=check_out,
        first_name="Morgan",
        last_name="Reed",
        email="morgan.reed@firm.com",
        phone="+1 555-123-4567",
        corporate_account="Global Consulting Group"
    )

    folios = folio_service.get_reservation_folios(res["reservation_id"])
    assert len(folios) == 2
    master_folio = next(f for f in folios if f["folio_type"] == "MASTER")
    incidental_folio = next(f for f in folios if f["folio_type"] == "INCIDENTAL")

    assert master_folio["payer_name"] == "Global Consulting Group"
    assert incidental_folio["payer_name"] == "Morgan Reed"

    # Post Restaurant charge to Incidental Folio
    charge = folio_service.post_charge(
        folio_id=incidental_folio["id"],
        category="RESTAURANT",
        description="Signature Seafood Dinner",
        amount=120.00,
        tax_rate=0.10,
        posted_by_user_id="user-frontdesk"
    )
    assert charge["total_item_cost"] == 132.00 # 120 + 12 tax

    # Test item splitting: transfer item to Master Folio
    split_res = folio_service.split_item_to_folio(
        item_id=charge["item_id"],
        target_folio_id=master_folio["id"],
        user_id="user-frontdesk"
    )
    assert split_res["success"] is True

    # Re-verify updated folios
    updated_folios = folio_service.get_reservation_folios(res["reservation_id"])
    m_folio = next(f for f in updated_folios if f["folio_type"] == "MASTER")
    inc_folio = next(f for f in updated_folios if f["folio_type"] == "INCIDENTAL")
    assert m_folio["balance"] == 132.00
    assert inc_folio["balance"] == 0.00

def test_single_click_night_audit_and_erp_export():
    # Execute Night Audit
    audit_res = night_audit_service.execute_night_audit(
        property_id="prop-horizon-miami",
        auditor_user_id="user-auditor"
    )
    assert audit_res["success"] is True
    assert "closed_business_date" in audit_res
    assert "new_business_date" in audit_res
    assert audit_res["total_rooms_occupied"] >= 1
    assert audit_res["total_room_revenue"] > 0

    # NetSuite CSV export
    netsuite_csv = erp_bridge.export_journal_netsuite(audit_res["audit_record_id"])
    assert "TranId,Date,Account,Debit,Credit,Memo" in netsuite_csv
    assert "4000 - Room Revenue" in netsuite_csv

    # QuickBooks IIF export
    qb_iif = erp_bridge.export_journal_quickbooks(audit_res["audit_record_id"])
    assert "!TRNS\tTRNSTYPE\tDATE\tACCNT" in qb_iif
    assert "GENERAL JOURNAL" in qb_iif

def test_immutable_audit_ledger_cryptographic_verification():
    verification = audit_service.verify_integrity()
    assert verification["valid"] is True
    assert verification["total_records"] > 0
    assert "Cryptographic integrity verified" in verification["message"]
