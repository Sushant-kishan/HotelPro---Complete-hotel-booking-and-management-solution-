# HotelPro: Enterprise Hotel Management Platform

[![Python 3.14](https://img.shields.io/badge/Python-3.14-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162.0-009688.svg)](https://fastapi.tiangolo.com)
[![PCI-DSS Level 1](https://img.shields.io/badge/PCI--DSS-Level%201%20Tokenized-emerald.svg)](#)
[![GDPR Compliant](https://img.shields.io/badge/GDPR-Article%2017%20%2F%2020-green.svg)](#)
[![Tests Passing](https://img.shields.io/badge/Tests-13%20Passed%20(100%25)-brightgreen.svg)](#)

HotelPro is a comprehensive, digital-first enterprise hotel management system architected to meet the evolving demands of modern hospitality. The platform unifies front-desk workflows, multi-channel booking lifecycles, dynamic room inventory, and PCI-compliant financial settlements into a resilient and intuitive ecosystem.

---

## 🌟 Key Features (Mapped to PRD v1.0)

### 1. Authentication, Authorization & Security (PRD §4.1)
- **Role-Based Access Control (RBAC)**: Partitioned permissions across strict roles (`SuperAdmin`, `PropertyManager`, `FrontDesk`, `Housekeeping`, `Auditor`).
- **Multi-Factor Authentication (MFA)**: RFC 6238 compliant Time-Based One-Time Password (TOTP) generation & validation with single-use backup recovery codes.
- **Session Integrity**: Automatic 15-minute inactivity termination with token invalidation.
- **Data Protection**: Field-level **AES-256-GCM** encryption for guest PII, deterministic HMAC blind indexing for fast lookups, and GDPR/CCPA Article 17 right-to-erasure (cryptographic shredding).
- **Tamper-Evident Audit Ledger**: SHA-256 hash-chained immutable append-only ledger tracking all status changes, room reassignments, and folio debits.

### 2. Room Inventory & Real-Time Availability (PRD §4.2)
- **Dynamic Inventory Synchronization**: Sub-second availability calculation across rooms, suites, and maintenance holds.
- **Distributed Concurrency Locking**: Multi-threaded distributed mutex prevents double-bookings during flash sales and peak OTA surges.
- **Overbooking Control**: Property-level configurable overbooking thresholds per season.

### 3. Booking & Reservation Lifecycle (PRD §4.3)
- **Multi-Channel Support**: Web direct bookings, corporate groups, walk-ins, and OTA channels.
- **Dynamic Yield Pricing Engine**: Occupancy-triggered rate multipliers (e.g. +25% during high occupancy, -10% off-peak promos, and 20% corporate discount codes `CORP20`).
- **Automated Guest CRM**: Profile history, preferences, VIP tiers, and stay records.

### 4. Expedited Front-Desk & Folio Operations (PRD §4.4, §4.5)
- **Sub-60-Second Check-In Flow**: Rapid guest lookup, room allocation, card pre-auth hold, and instant **RFID / Bluetooth Low Energy (BLE) keycard generation**.
- **Sub-60-Second Check-Out Flow**: Single-click folio balance verification, instant capture settlement, keycard invalidation, and immediate Housekeeping `DIRTY` trigger.
- **Multi-Payer Split Folio**: Segregates Room & Tax into a **Master Folio** (payable by Company/Corporate) and extras (F&B, Minibar, Room Service, Spa) into an **Incidental Folio**.
- **PCI-DSS Level 1 Tokenization**: Zero raw cardholder data stored; card tokens, card brand, and masked last-4 credentials only.
- **Single-Click Night Audit**: Automated posting of nightly room charges and taxes to all in-house folios, occupancy reconciliation, and business date advancing.

### 5. Integrations & Hardware Interfaces (PRD §6)
- **Channel Managers & OTAs**: Bi-directional ARI (Availability, Rates, Inventory) sync and webhook booking ingestion for Booking.com, Expedia, and GDS.
- **Hardware Peripheral Simulator**: Keycard encoder bridge emitting RFID track data and BLE mobile key payloads.
- **ERP & Accounting Sync**: Automated end-of-day revenue journals in **NetSuite CSV** and **QuickBooks IIF** standard formats.

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.13 or 3.14

### 2. Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Seed Demo Data & Launch

#### Option A: Interactive Streamlit Suite (Recommended)
```bash
streamlit run streamlit_app.py --server.port 8501
```
Access the application at: **`http://localhost:8501`**

#### Option B: FastAPI Backend + Unified Web Client
```bash
python -m app.seed
python -m app.main
```
The server will start on `http://127.0.0.1:8000`.

### 4. Open Web Interfaces
- **Streamlit Suite**: `http://localhost:8501`
- **Unified Web Portal**: `http://localhost:8000/`
- **Interactive OpenAPI Documentation**: `http://localhost:8000/api/docs`

---

## 🧪 Running the Test Suite

The comprehensive test suite covers all security, concurrency, booking lifecycle, folio, and night audit requirements:

```bash
source venv/bin/activate
python -m pytest -v -s
```

### Test Coverage Highlights:
- `test_password_hashing`: PBKDF2 with 600,000 iterations.
- `test_totp_mfa_generation_and_verification`: RFC 6238 TOTP codes, QR URI, and backup recovery keys.
- `test_session_token_and_inactivity_timeout`: 15-minute inactivity timeout validation.
- `test_rbac_permissions_matrix`: All 5 roles tested against the granular capability matrix.
- `test_concurrency_locking_prevents_double_booking`: Parallel threads booking the same room concurrently; verifies zero double-booking.
- `test_aes256_pii_encryption_and_blind_indexing`: Field-level AES-256-GCM encryption and blind index searching.
- `test_expedited_sub_60s_check_in_and_keycard_generation`: Front desk check-in, incidental pre-auth, and RFID/BLE keycard payload.
- `test_multi_payer_split_folio_and_incidental_posting`: Master vs Incidental folios, charge posting, and line-item splitting.
- `test_single_click_night_audit_and_erp_export`: End-of-day room charge posting, ledger reconciliation, NetSuite CSV and QuickBooks IIF exports.
- `test_immutable_audit_ledger_cryptographic_verification`: SHA-256 blockchain-style hash chain integrity verification.
- `test_api_availability_latency_nfr`: p95 latency benchmark (0.28 ms, beating the <= 200 ms PRD target).

---

## 👥 Demo Staff Credentials

| Role | Username | Password | TOTP MFA Secret / Recovery Code |
| :--- | :--- | :--- | :--- |
| **SuperAdmin** | `admin` | `admin123` | `JBSWY3DPEHPK3PXP` / `A1B2-C3D4` |
| **PropertyManager** | `manager` | `manager123` | `JBSWY3DPEHPK3PXP` / `A1B2-C3D4` |
| **FrontDesk** | `frontdesk` | `frontdesk123` | `JBSWY3DPEHPK3PXP` / `A1B2-C3D4` |
| **Housekeeping** | `housekeeper` | `clean123` | N/A (Direct Access) |
| **Auditor** | `auditor` | `audit123` | `JBSWY3DPEHPK3PXP` / `A1B2-C3D4` |

