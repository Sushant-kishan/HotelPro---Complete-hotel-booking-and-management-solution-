"""
HotelPro - Enterprise Hotel Management Platform
Interactive Streamlit Application (PRD v1.0)
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime, date, timedelta

# Core HotelPro Modules
from app.database import init_db, get_db
from app.seed import seed_demo_data
from app.config import settings
from app.services.inventory_engine import inventory_engine
from app.services.booking_service import booking_service
from app.services.frontdesk_service import frontdesk_service
from app.services.folio_service import folio_service
from app.services.housekeeping_service import housekeeping_service
from app.services.night_audit_service import night_audit_service
from app.services.erp_sync import erp_bridge
from app.security.crypto import pii_service
from app.security.totp import totp_service
from app.security.audit import audit_service
from app.security.rbac import Role, Permission, has_permission

# Page Configuration
st.set_page_config(
    page_title="HotelPro | Enterprise Hotel Suite",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Enterprise CSS
st.markdown("""
<style>
    .metric-card {
        background: #ffffff;
        padding: 18px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge-clean { background-color: #d1fae5; color: #065f46; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-inspected { background-color: #dbeafe; color: #1e40af; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-dirty { background-color: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-progress { background-color: #fef3c7; color: #92400e; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
    .badge-ooo { background-color: #f1f5f9; color: #475569; padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px; }
</style>
""", unsafe_allow_html=True)

# Ensure Database and Seed Data
init_db()
seed_demo_data()

# Fetch active property details
with get_db() as db:
    prop = db.execute("SELECT * FROM properties LIMIT 1").fetchone()
    property_id = prop["id"]
    property_name = prop["name"]
    property_code = prop["code"]
    current_business_date = prop["current_business_date"]

# -------------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------------
st.sidebar.markdown(f"### 🏨 **HotelPro Enterprise**")
st.sidebar.caption(f"**{property_name}** `[{property_code}]`")
st.sidebar.info(f"📅 **Business Date:** `{current_business_date}`")

st.sidebar.markdown("---")
st.sidebar.markdown("#### 👤 **Active Staff Persona**")
role_selection = st.sidebar.selectbox(
    "Switch RBAC Role:",
    [
        "Front Desk Lead (Marcus Chen)",
        "General Manager (Elena Rostova)",
        "Housekeeping Lead (Rosa Morales)",
        "Night Auditor (David Sterling)",
        "Super Admin (Alex Vance)",
        "Guest Self-Service Portal"
    ]
)

role_map = {
    "Front Desk Lead (Marcus Chen)": ("FrontDesk", "user-frontdesk"),
    "General Manager (Elena Rostova)": ("PropertyManager", "user-manager"),
    "Housekeeping Lead (Rosa Morales)": ("Housekeeping", "user-housekeeper"),
    "Night Auditor (David Sterling)": ("Auditor", "user-auditor"),
    "Super Admin (Alex Vance)": ("SuperAdmin", "user-admin"),
    "Guest Self-Service Portal": ("Guest", None)
}
current_role, current_user_id = role_map[role_selection]
st.sidebar.success(f"Role: **{current_role}** | 🔒 Zero-Trust Active")

# Real-time Quick Metrics
with get_db() as db:
    in_house_count = db.execute("SELECT COUNT(*) as c FROM reservations WHERE property_id = ? AND status = 'CHECKED_IN'", (property_id,)).fetchone()["c"]
    total_rooms = db.execute("SELECT COUNT(*) as c FROM rooms WHERE property_id = ?", (property_id,)).fetchone()["c"]
    dirty_count = db.execute("SELECT COUNT(*) as c FROM rooms WHERE property_id = ? AND housekeeping_status = 'DIRTY'", (property_id,)).fetchone()["c"]

st.sidebar.markdown("---")
st.sidebar.metric("Occupancy", f"{int((in_house_count / max(1, total_rooms)) * 100)}%", f"{in_house_count}/{total_rooms} Rooms")
st.sidebar.metric("Turnover Queue", f"{dirty_count} Dirty Rooms")

# Navigation Menu
st.sidebar.markdown("---")
nav_choice = st.sidebar.radio(
    "Operational Modules:",
    [
        "⚡ Sub-60s Front Desk Operations",
        "🛎️ Guest Booking & Yield Engine",
        "📱 Guest Folio & Digital Key",
        "🧹 Housekeeping Board",
        "💳 Multi-Payer Split Folios",
        "🌙 Single-Click Night Audit & ERP",
        "🛡️ Tamper-Evident SHA-256 Ledger",
        "🔒 TOTP MFA & Security Center"
    ]
)

# -------------------------------------------------------------
# MODULE 1: SUB-60s FRONT DESK OPERATIONS
# -------------------------------------------------------------
if nav_choice == "⚡ Sub-60s Front Desk Operations":
    st.title("⚡ Sub-60-Second Front Desk Operations")
    st.caption("Expedited check-in/out, automated room allocation, incidental pre-authorizations, and native RFID/BLE keycard encoder integration.")

    tab_arrivals, tab_departures = st.tabs(["🛎️ Today's Arrivals (Expedited Check-In)", "🚪 Today's Departures (Expedited Check-Out)"])

    # Arrivals Tab
    with tab_arrivals:
        arrivals = frontdesk_service.find_arrivals(property_id)
        if not arrivals:
            st.info("No pending arrivals for today.")
        else:
            df_arrivals = pd.DataFrame([
                {
                    "Reference": a["booking_reference"],
                    "Guest Name": a["guest_name"],
                    "Room Category": a["room_type_name"],
                    "Dates": f"{a['check_in_date']} → {a['check_out_date']}",
                    "Notes": a.get("special_requests") or "None",
                    "res_id": a["id"],
                    "room_type_id": a["room_type_id"]
                }
                for a in arrivals
            ])
            st.dataframe(df_arrivals.drop(columns=["res_id", "room_type_id"]), use_container_width=True)

            st.markdown("#### ⚡ Execute Rapid Check-In (< 60s Flow)")
            with st.form("checkin_form"):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    selected_ref = st.selectbox("Select Arriving Guest:", [a["booking_reference"] + " - " + a["guest_name"] for a in arrivals])
                    chosen_res = next(a for a in arrivals if a["booking_reference"] in selected_ref)
                
                # Fetch assignable rooms
                assignable = frontdesk_service.get_assignable_rooms(property_id, chosen_res["room_type_id"])
                with col2:
                    if assignable:
                        room_opts = {f"Room {r['room_number']} (Floor {r['floor']} • {r['housekeeping_status']})": r["id"] for r in assignable}
                        selected_room_label = st.selectbox("Assign Clean / Inspected Room:", list(room_opts.keys()))
                        selected_room_id = room_opts[selected_room_label]
                    else:
                        st.error("No clean rooms available for this category!")
                        selected_room_id = None

                with col3:
                    incidental_hold = st.number_input("Pre-Auth Hold ($):", value=100.0, step=25.0)

                submit_checkin = st.form_submit_button("⚡ Authorize Pre-Auth & Issue Keycard", type="primary")

                if submit_checkin:
                    if not selected_room_id:
                        st.error("Cannot check in without an available room.")
                    else:
                        res = frontdesk_service.expedited_check_in(
                            reservation_id=chosen_res["id"],
                            room_id=selected_room_id,
                            card_token="tok_pci_visa_frontdesk_hold",
                            incidental_deposit_amount=incidental_hold,
                            staff_user_id=current_user_id
                        )
                        st.success(f"✅ Check-in complete! Room {res['room_number']} assigned.")
                        
                        # Display hardware keycard encoder payload
                        kc = res["keycard"]
                        with st.expander("🔑 Native Keycard Encoder Hardware Payload (Emitted to RFID/BLE Bridge)", expanded=True):
                            st.json(kc)
                        st.rerun()

    # Departures Tab
    with tab_departures:
        departures = frontdesk_service.find_departures(property_id)
        if not departures:
            st.info("No guests scheduled for departure today.")
        else:
            df_dep = pd.DataFrame([
                {
                    "Room": f"Room {d.get('room_number', 'N/A')}",
                    "Guest Name": d["guest_name"],
                    "Reference": d["booking_reference"],
                    "Balance Due ($)": f"${d['total_open_balance']:.2f}",
                    "res_id": d["id"]
                }
                for d in departures
            ])
            st.dataframe(df_dep.drop(columns=["res_id"]), use_container_width=True)

            st.markdown("#### ⚡ Settle Balance & Complete Check-Out")
            with st.form("checkout_form"):
                selected_dep_label = st.selectbox("Select Departing Room:", [f"Room {d.get('room_number')} - {d['guest_name']} (${d['total_open_balance']:.2f} due)" for d in departures])
                chosen_dep = next(d for d in departures if f"Room {d.get('room_number')}" in selected_dep_label)
                submit_checkout = st.form_submit_button("⚡ Settle Folios & Finalize Check-Out", type="primary")

                if submit_checkout:
                    res = frontdesk_service.expedited_check_out(
                        reservation_id=chosen_dep["id"],
                        staff_user_id=current_user_id
                    )
                    st.success(f"✅ Check-out finalized! Room {res['room_number']} set to DIRTY for Housekeeping turnover. Keycard deactivated.")
                    st.rerun()

# -------------------------------------------------------------
# MODULE 2: GUEST BOOKING & DYNAMIC YIELD PRICING ENGINE
# -------------------------------------------------------------
elif nav_choice == "🛎️ Guest Booking & Yield Engine":
    st.title("🛎️ Guest Booking & Dynamic Yield Pricing Engine")
    st.caption("Live room search with concurrency-locked reservations and real-time yield multipliers.")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        cin = st.date_input("Check-In Date", value=date.today())
    with col2:
        cout = st.date_input("Check-Out Date", value=date.today() + timedelta(days=3))
    with col3:
        promo = st.text_input("Promo / Corporate Code", placeholder="e.g. CORP20, DIRECT10")

    if cout <= cin:
        st.error("Check-out date must be after check-in date.")
    else:
        results = inventory_engine.get_all_room_types_availability(property_id, cin.isoformat(), cout.isoformat())
        
        st.markdown("### 🛏️ Available Categories & Rates")
        cols = st.columns(len(results))
        for idx, cat in enumerate(results):
            with cols[idx]:
                rate = cat["dynamic_nightly_rate"]
                if promo.strip().upper() == "CORP20":
                    rate = round(rate * 0.80, 2)
                
                st.markdown(f"#### **{cat['name']}**")
                st.caption(cat.get("description") or "")
                st.metric(
                    label="Nightly Rate",
                    value=f"${rate}/night",
                    delta=f"{cat['rooms_remaining']} left" if cat["available"] else "Sold Out",
                    delta_color="normal" if cat["available"] else "inverse"
                )
                if cat["dynamic_nightly_rate"] > cat["default_base_rate"]:
                    st.caption("⚡ *High Occupancy Yield Surge (+25%)*")
                if promo.strip().upper() == "CORP20":
                    st.caption("🏷️ *20% Corporate Rate Applied*")

        st.markdown("---")
        st.markdown("### 📝 Instant Reservation Booking")
        with st.form("direct_booking_form"):
            c1, c2 = st.columns(2)
            with c1:
                first_name = st.text_input("First Name", "Julian")
                last_name = st.text_input("Last Name", "Mercer")
                email = st.text_input("Email (AES-256 Encrypted)", "julian.mercer@corporate.com")
            with c2:
                phone = st.text_input("Phone (Blind Indexed)", "+1 305-555-8910")
                avail_cats = {c["name"]: c["id"] for c in results if c["available"]}
                chosen_cat_name = st.selectbox("Select Room Category:", list(avail_cats.keys()))
                channel = st.selectbox("Booking Channel:", ["DIRECT_WEB", "CORPORATE", "BOOKING_COM", "EXPEDIA"])

            special_req = st.text_area("Special Requests / Dietary Notes", "Prefers high floor, quiet ocean side.")
            book_btn = st.form_submit_button("💳 Confirm Booking & Initialize Split Folios", type="primary")

            if book_btn:
                try:
                    res = booking_service.create_reservation(
                        tenant_id=prop["tenant_id"],
                        property_id=property_id,
                        room_type_id=avail_cats[chosen_cat_name],
                        check_in_date=cin.isoformat(),
                        check_out_date=cout.isoformat(),
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        phone=phone,
                        channel=channel,
                        discount_code=promo or None,
                        special_requests=special_req
                    )
                    st.success(f"🎉 Reservation Confirmed! Code: **{res['booking_reference']}**")
                    st.json(res)
                except Exception as e:
                    st.error(f"Booking Error: {str(e)}")

# -------------------------------------------------------------
# MODULE 3: GUEST FOLIO & DIGITAL KEY LOOKUP
# -------------------------------------------------------------
elif nav_choice == "📱 Guest Folio & Digital Key":
    st.title("📱 Guest Folio Statement & Digital Keycard")
    st.caption("Look up any active or past reservation to view live folio balances and mobile key credentials.")

    lookup_ref = st.text_input("Enter Booking Reference Code:", value="HP-", placeholder="e.g. HP-2026-9B3F")
    if lookup_ref and len(lookup_ref) > 4:
        with get_db() as db:
            res = db.execute(
                """
                SELECT r.*, rt.name as room_type_name, g.encrypted_first_name, g.encrypted_last_name,
                       g.encrypted_email, g.encrypted_phone, rm.room_number, rm.active_keycard_token
                FROM reservations r
                JOIN room_types rt ON r.room_type_id = rt.id
                JOIN guests g ON r.guest_id = g.id
                LEFT JOIN rooms rm ON r.assigned_room_id = rm.id
                WHERE r.booking_reference = ?
                """,
                (lookup_ref.strip().upper(),)
            ).fetchone()

        if not res:
            st.warning("No reservation found matching this reference code.")
        else:
            guest_name = f"{pii_service.decrypt(res['encrypted_first_name'])} {pii_service.decrypt(res['encrypted_last_name'])}"
            st.markdown(f"### Stay for **{guest_name}** (`{res['booking_reference']}`)")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Status", res["status"])
            c2.metric("Room", f"Room {res['room_number']}" if res["room_number"] else "Unassigned")
            c3.metric("Check-In", res["check_in_date"])
            c4.metric("Check-Out", res["check_out_date"])

            # Mobile Keycard
            if res["status"] == "CHECKED_IN" and res["room_number"]:
                st.markdown("---")
                st.success(f"📱 **Mobile Keycard Active for Room {res['room_number']}**")
                st.code(f"BLE Auth Key: {res['active_keycard_token']}\nTap mobile device to reader to unlock room.")

            # Folios Breakdown
            st.markdown("---")
            st.markdown("#### 📄 Split Folio Statements")
            folios = folio_service.get_reservation_folios(res["id"])
            for f in folios:
                with st.expander(f"{f['folio_type']} Folio - Payer: {f['payer_name']} (Balance: ${f['balance']:.2f})", expanded=True):
                    if f["items"]:
                        df_items = pd.DataFrame([
                            {"Category": it["category"], "Description": it["description"], "Amount": f"${it['amount']:.2f}", "Tax": f"${it['tax_amount']:.2f}"}
                            for it in f["items"]
                        ])
                        st.table(df_items)
                    else:
                        st.caption("No charges posted to this folio yet.")

# -------------------------------------------------------------
# MODULE 4: REAL-TIME HOUSEKEEPING BOARD
# -------------------------------------------------------------
elif nav_choice == "🧹 Housekeeping Board":
    st.title("🧹 Real-Time Housekeeping & Turnaround Board")
    st.caption("Monitor and transition room cleanliness states with instant sub-second front-desk synchronization.")

    board = housekeeping_service.get_room_board(property_id)
    
    # Summary Pills
    clean_n = sum(1 for r in board if r["housekeeping_status"] == "CLEAN")
    inspected_n = sum(1 for r in board if r["housekeeping_status"] == "INSPECTED")
    dirty_n = sum(1 for r in board if r["housekeeping_status"] == "DIRTY")
    progress_n = sum(1 for r in board if r["housekeeping_status"] == "IN_PROGRESS")
    ooo_n = sum(1 for r in board if r["housekeeping_status"] == "OUT_OF_ORDER")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Clean", clean_n)
    col2.metric("Inspected", inspected_n)
    col3.metric("In Progress", progress_n)
    col4.metric("Dirty", dirty_n)
    col5.metric("Out of Order", ooo_n)

    st.markdown("---")
    st.markdown("#### 🛏️ Physical Room States")
    
    # Display room cards in responsive columns
    cols = st.columns(4)
    for idx, room in enumerate(board):
        with cols[idx % 4]:
            with st.container(border=True):
                st.markdown(f"### **Room {room['room_number']}**")
                st.caption(f"Floor {room['floor']} • {room['room_type_name']}")
                st.markdown(f"Status: **{room['housekeeping_status']}**")
                st.caption(f"Occupancy: *{room['operational_status']}*")
                
                # Status Change Selectbox
                new_st = st.selectbox(
                    f"Update {room['room_number']}:",
                    ["CLEAN", "INSPECTED", "DIRTY", "IN_PROGRESS", "OUT_OF_ORDER"],
                    index=["CLEAN", "INSPECTED", "DIRTY", "IN_PROGRESS", "OUT_OF_ORDER"].index(room["housekeeping_status"]),
                    key=f"hk_select_{room['id']}"
                )
                if new_st != room["housekeeping_status"]:
                    housekeeping_service.update_room_status(room["id"], new_st, current_user_id)
                    st.success(f"Room {room['room_number']} updated!")
                    st.rerun()

# -------------------------------------------------------------
# MODULE 5: MULTI-PAYER SPLIT FOLIOS & INCIDENTAL BILLING
# -------------------------------------------------------------
elif nav_choice == "💳 Multi-Payer Split Folios":
    st.title("💳 Multi-Payer Split Folio & Incidental Manager")
    st.caption("Partition room rates to corporate Master Folios and F&B/minibar incidentals to personal guest folios.")

    with get_db() as db:
        active_stays = db.execute(
            """
            SELECT r.id, r.booking_reference, rm.room_number, g.encrypted_first_name, g.encrypted_last_name
            FROM reservations r
            JOIN guests g ON r.guest_id = g.id
            JOIN rooms rm ON r.assigned_room_id = rm.id
            WHERE r.property_id = ? AND r.status = 'CHECKED_IN'
            """,
            (property_id,)
        ).fetchall()

    if not active_stays:
        st.info("No in-house guests currently checked in.")
    else:
        stay_opts = {
            f"Room {s['room_number']} - {pii_service.decrypt(s['encrypted_first_name'])} {pii_service.decrypt(s['encrypted_last_name'])} ({s['booking_reference']})": s["id"]
            for s in active_stays
        }
        chosen_stay_label = st.selectbox("Select In-House Guest:", list(stay_opts.keys()))
        chosen_stay_id = stay_opts[chosen_stay_label]

        folios = folio_service.get_reservation_folios(chosen_stay_id)
        
        # Display folios side by side
        col1, col2 = st.columns(2)
        for idx, f in enumerate(folios):
            target_col = col1 if idx == 0 else col2
            with target_col:
                with st.container(border=True):
                    st.markdown(f"### **{f['folio_type']} FOLIO**")
                    st.caption(f"Payer: **{f['payer_name']}** ({f['payer_type']}) | Status: **{f['status']}**")
                    st.markdown(f"Total Charges: **${f['total_charges']:.2f}** | Payments: **${f['total_payments']:.2f}**")
                    st.markdown(f"#### Outstanding Balance: **${f['balance']:.2f}**")

                    if f["items"]:
                        for it in f["items"]:
                            st.text(f"• {it['description']} ({it['category']}): ${it['amount'] + it['tax_amount']:.2f}")
                            # Button to move item to other folio
                            other_f = next((o for o in folios if o["id"] != f["id"]), None)
                            if other_f:
                                if st.button(f"➡️ Move to {other_f['folio_type']}", key=f"split_btn_{it['id']}"):
                                    folio_service.split_item_to_folio(it["id"], other_f["id"], current_user_id)
                                    st.success("Item moved!")
                                    st.rerun()
                    else:
                        st.caption("No charges on this folio.")

                    # Settle balance
                    if f["balance"] > 0:
                        if st.button(f"💳 Settle Balance (${f['balance']:.2f})", key=f"settle_{f['id']}", type="primary"):
                            folio_service.process_payment(
                                folio_id=f["id"],
                                amount=f["balance"],
                                card_token="tok_pci_visa_streamlit",
                                card_brand="Visa",
                                card_last4="4242",
                                transaction_type="CAPTURE",
                                user_id=current_user_id
                            )
                            st.success(f"Captured ${f['balance']:.2f} via PCI-DSS tokenized bridge!")
                            st.rerun()

        st.markdown("---")
        st.markdown("#### ➕ Post New Incidental Charge")
        with st.form("post_charge_form"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                target_folio = st.selectbox("Post to Folio:", [f"{f['folio_type']} ({f['payer_name']})" for f in folios])
                chosen_f_id = next(f["id"] for f in folios if f["folio_type"] in target_folio)
            with c2:
                cat = st.selectbox("Category:", ["RESTAURANT", "MINIBAR", "ROOM_SERVICE", "SPA", "PARKING"])
            with c3:
                desc = st.text_input("Item Description:", "Poolside Cocktails & Appetizers")
            with c4:
                amt = st.number_input("Amount ($):", value=45.00, step=5.0)

            if st.form_submit_button("Post Incidental Charge", type="primary"):
                folio_service.post_charge(
                    folio_id=chosen_f_id,
                    category=cat,
                    description=desc,
                    amount=amt,
                    tax_rate=0.10,
                    posted_by_user_id=current_user_id
                )
                st.success("Charge posted!")
                st.rerun()

# -------------------------------------------------------------
# MODULE 6: SINGLE-CLICK NIGHT AUDIT & ERP FINANCIAL SYNC
# -------------------------------------------------------------
elif nav_choice == "🌙 Single-Click Night Audit & ERP":
    st.title("🌙 Single-Click Night Audit & Financial Reconciliation")
    st.caption("Automated posting of daily room charges & taxes, occupancy audit, and NetSuite/QuickBooks general ledger sync.")

    check = night_audit_service.get_pre_audit_checklist(property_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Operational Date", check["current_business_date"])
    c2.metric("In-House Rooms", check["in_house_reservations_count"])
    c3.metric("Pending Arrivals", check["pending_arrivals_count"])
    c4.metric("Overdue Departures", check["overdue_departures_count"])

    st.markdown("---")
    st.info("Executing Night Audit will automatically charge room rates to all in-house Master Folios, reconcile revenues, generate journal entries, and advance the hotel operational date.")

    if st.button("🌙 Execute End-of-Day Night Audit Roll-Over", type="primary"):
        res = night_audit_service.execute_night_audit(property_id, current_user_id)
        st.balloons()
        st.success(f"🎉 Night Audit Complete! Closed date: {res['closed_business_date']}. Operational date advanced to: {res['new_business_date']}.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Occupancy Rate", f"{res['occupancy_rate']}%")
        c2.metric("Room Revenue", f"${res['total_room_revenue']:.2f}")
        c3.metric("Taxes Posted", f"${res['total_tax_revenue']:.2f}")

        # Download ERP Journals
        st.markdown("#### 📥 Download Reconciled ERP Accounting Journals")
        col_ns, col_qb = st.columns(2)
        with col_ns:
            ns_csv = erp_bridge.export_journal_netsuite(res["audit_record_id"])
            st.download_button(
                "📥 Download NetSuite CSV Journal",
                data=ns_csv,
                file_name=f"netsuite_journal_{res['closed_business_date']}.csv",
                mime="text/csv"
            )
        with col_qb:
            qb_iif = erp_bridge.export_journal_quickbooks(res["audit_record_id"])
            st.download_button(
                "📥 Download QuickBooks IIF Journal",
                data=qb_iif,
                file_name=f"quickbooks_journal_{res['closed_business_date']}.iif",
                mime="text/plain"
            )

# -------------------------------------------------------------
# MODULE 7: TAMPER-EVIDENT SHA-256 AUDIT LEDGER
# -------------------------------------------------------------
elif nav_choice == "🛡️ Tamper-Evident SHA-256 Ledger":
    st.title("🛡️ Tamper-Evident SHA-256 Immutable Audit Ledger")
    st.caption("Cryptographically chained audit trail capturing every room status change, folio update, and financial charge.")

    if st.button("🛡️ Verify Hash-Chain Integrity Across All Blocks", type="primary"):
        verify_res = audit_service.verify_integrity()
        if verify_res["valid"]:
            st.success(f"✅ Cryptographic Integrity Validated! {verify_res['total_records']} immutable blocks verified with zero tampering.")
        else:
            st.error(f"⚠️ Tampering Detected at Block #{verify_res['tampered_id']}! {verify_res['reason']}")

    with get_db() as db:
        logs = db.execute("SELECT id, action, user_role, entity_type, entity_id, record_hash, prev_hash, created_at FROM audit_logs ORDER BY id DESC LIMIT 50").fetchall()
    
    if logs:
        df_logs = pd.DataFrame([
            {
                "Block #": l["id"],
                "Action": l["action"],
                "Role": l["user_role"] or "System",
                "Entity": f"{l['entity_type']} ({l['entity_id'][:8]}...)",
                "SHA-256 Signature": l["record_hash"][:16] + "...",
                "Timestamp": l["created_at"]
            }
            for l in logs
        ])
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("No audit logs recorded yet.")

# -------------------------------------------------------------
# MODULE 8: TOTP MFA & SECURITY CENTER
# -------------------------------------------------------------
elif nav_choice == "🔒 TOTP MFA & Security Center":
    st.title("🔒 TOTP Multi-Factor Authentication & Zero-Trust Governance")
    st.caption("RFC 6238 compliant TOTP generator, validator, and emergency recovery key manager.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🔐 Generate / Test TOTP 6-Digit Codes")
        demo_secret = "JBSWY3DPEHPK3PXP"
        current_totp = totp_service.get_totp_code(demo_secret)
        st.metric("Live 6-Digit TOTP Code", current_totp, "RFC 6238 Standard (30s window)")
        st.caption(f"Base32 Secret: `{demo_secret}`")
        st.caption(f"Provisioning URI: `{totp_service.get_provisioning_uri(demo_secret, 'marcus_frontdesk')}`")

    with col2:
        st.markdown("#### 🔑 Single-Use Emergency Recovery Codes")
        st.code("A1B2-C3D4\nE5F6-G7H8\nJ9K0-L1M2\nN3P4-Q5R6")
        st.caption("Emergency backup codes bypass authenticator downtime in compliance with PRD §4.1.")

