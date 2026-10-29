"""
Automated Test Suite for API Handlers and Latency Benchmarks
PRD Section 5: API Response Latency (95th percentile <= 200ms).
"""
import time
import pytest
from app.api.inventory_router import check_availability
from app.api.booking_router import book_reservation, lookup_reservation, ReservationCreateRequest

def test_api_availability_latency_nfr():
    """Validates PRD Section 5 requirement: Latency <= 200ms."""
    durations = []
    for _ in range(20):
        t0 = time.perf_counter()
        res = check_availability(
            property_id="prop-horizon-miami",
            check_in_date="2027-07-01",
            check_out_date="2027-07-04"
        )
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1000) # milliseconds
        assert "categories" in res

    durations.sort()
    p95_index = int(len(durations) * 0.95)
    p95_latency = durations[p95_index]
    print(f"\nAPI check_availability p95 latency: {p95_latency:.2f} ms")
    assert p95_latency <= 200.0, f"p95 latency {p95_latency}ms exceeded 200ms target"

def test_guest_booking_and_lookup_flow():
    # 1. Book a room via API
    book_payload = ReservationCreateRequest(
        property_id="prop-horizon-miami",
        room_type_id="rt-std-queen",
        check_in_date="2027-08-10",
        check_out_date="2027-08-13",
        first_name="Eleanor",
        last_name="Pena",
        email="eleanor.pena@example.com",
        phone="+1 555-443-2211",
        channel="DIRECT_WEB"
    )
    t0 = time.perf_counter()
    data = book_reservation(book_payload)
    t1 = time.perf_counter()
    booking_latency = (t1 - t0) * 1000
    print(f"\nAPI book_reservation latency: {booking_latency:.2f} ms")
    assert booking_latency <= 200.0

    ref = data["booking_reference"]
    assert "HP-" in ref

    # 2. Lookup reservation & folios
    t0 = time.perf_counter()
    lookup_data = lookup_reservation(ref)
    t1 = time.perf_counter()
    lookup_latency = (t1 - t0) * 1000
    print(f"\nAPI lookup_reservation latency: {lookup_latency:.2f} ms")
    assert lookup_latency <= 200.0

    assert lookup_data["booking_reference"] == ref
    assert lookup_data["guest_first_name"] == "Eleanor"
    assert len(lookup_data["folios"]) == 2 # Master & Incidental split folios
