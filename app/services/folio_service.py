"""
HotelPro Folio & Split-Billing Operations Service
PRD Section 4.4, 4.5: Multi-payer folio splitting, automated posting for F&B/room service
incidentals, pre-auth holds, and check-out folio capture.
"""
import uuid
from typing import Dict, Any, List, Optional
from app.database import get_db
from app.services.payment_bridge import payment_bridge
from app.security.audit import audit_service

class FolioService:
    @classmethod
    def create_reservation_folios(
        cls,
        reservation_id: str,
        guest_name: str,
        corporate_payer: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Initializes split folios for a newly confirmed booking:
        - Master Folio (Room & Tax - payable by Guest or Corporate)
        - Incidental Folio (F&B, Minibar, Spa - payable by In-House Guest)
        """
        master_folio_id = str(uuid.uuid4())
        incidental_folio_id = str(uuid.uuid4())

        with get_db() as db:
            # 1. Master Folio
            payer_type = "CORPORATE" if corporate_payer else "GUEST"
            payer_name = corporate_payer if corporate_payer else guest_name
            db.execute(
                """
                INSERT INTO folios (id, reservation_id, folio_type, payer_name, payer_type, status, total_charges, total_payments, balance)
                VALUES (?, ?, 'MASTER', ?, ?, 'OPEN', 0.0, 0.0, 0.0)
                """,
                (master_folio_id, reservation_id, payer_name, payer_type)
            )

            # 2. Incidental Folio
            db.execute(
                """
                INSERT INTO folios (id, reservation_id, folio_type, payer_name, payer_type, status, total_charges, total_payments, balance)
                VALUES (?, ?, 'INCIDENTAL', ?, 'GUEST', 'OPEN', 0.0, 0.0, 0.0)
                """,
                (incidental_folio_id, reservation_id, guest_name)
            )

        return {
            "master_folio_id": master_folio_id,
            "incidental_folio_id": incidental_folio_id
        }

    @classmethod
    def post_charge(
        cls,
        folio_id: str,
        category: str,
        description: str,
        amount: float,
        tax_rate: float = 0.10,
        posted_by_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Posts a charge (e.g. Room Charge, Restaurant, Minibar, Room Service) to a specific folio.
        Updates folio balance and records an immutable audit ledger block.
        """
        item_id = str(uuid.uuid4())
        tax_amount = round(amount * tax_rate, 2)
        total_item_cost = round(amount + tax_amount, 2)

        with get_db() as db:
            # Check folio status
            folio = db.execute("SELECT * FROM folios WHERE id = ?", (folio_id,)).fetchone()
            if not folio:
                raise ValueError("Folio not found.")
            if folio["status"] == "SETTLED":
                raise ValueError("Cannot post charges to an already settled folio.")

            # Insert line item
            db.execute(
                """
                INSERT INTO folio_items (id, folio_id, category, description, amount, tax_amount, posted_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, folio_id, category, description, amount, tax_amount, posted_by_user_id)
            )

            # Update folio totals
            new_charges = round(folio["total_charges"] + total_item_cost, 2)
            new_balance = round(new_charges - folio["total_payments"], 2)
            db.execute(
                """
                UPDATE folios
                SET total_charges = ?, balance = ?
                WHERE id = ?
                """,
                (new_charges, new_balance, folio_id)
            )

            # Fetch reservation and property id for audit log
            res = db.execute(
                "SELECT property_id FROM reservations WHERE id = ?",
                (folio["reservation_id"],)
            ).fetchone()
            prop_id = res["property_id"] if res else None

        audit_service.log_event(
            tenant_id="default-tenant",
            property_id=prop_id,
            user_id=posted_by_user_id,
            user_role="Staff",
            action="POST_FOLIO_CHARGE",
            entity_type="FolioItem",
            entity_id=item_id,
            payload={
                "folio_id": folio_id,
                "category": category,
                "description": description,
                "amount": amount,
                "tax_amount": tax_amount,
                "total_charged": total_item_cost,
                "new_balance": new_balance
            }
        )

        return {
            "item_id": item_id,
            "folio_id": folio_id,
            "category": category,
            "amount": amount,
            "tax_amount": tax_amount,
            "total_item_cost": total_item_cost,
            "folio_balance": new_balance
        }

    @classmethod
    def split_item_to_folio(cls, item_id: str, target_folio_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Moves a charge item from one folio to another (e.g. moving a minibar charge to guest incidental folio).
        Recalculates balances for both source and destination folios.
        """
        with get_db() as db:
            item = db.execute("SELECT * FROM folio_items WHERE id = ?", (item_id,)).fetchone()
            if not item:
                raise ValueError("Folio item not found.")
            source_folio_id = item["folio_id"]
            if source_folio_id == target_folio_id:
                raise ValueError("Target folio must differ from current source folio.")

            item_cost = round(item["amount"] + item["tax_amount"], 2)

            source_folio = db.execute("SELECT * FROM folios WHERE id = ?", (source_folio_id,)).fetchone()
            target_folio = db.execute("SELECT * FROM folios WHERE id = ?", (target_folio_id,)).fetchone()

            # Move item
            db.execute("UPDATE folio_items SET folio_id = ? WHERE id = ?", (target_folio_id, item_id))

            # Update source
            src_charges = round(source_folio["total_charges"] - item_cost, 2)
            src_balance = round(src_charges - source_folio["total_payments"], 2)
            db.execute("UPDATE folios SET total_charges = ?, balance = ? WHERE id = ?", (src_charges, src_balance, source_folio_id))

            # Update target
            tgt_charges = round(target_folio["total_charges"] + item_cost, 2)
            tgt_balance = round(tgt_charges - target_folio["total_payments"], 2)
            db.execute("UPDATE folios SET total_charges = ?, balance = ? WHERE id = ?", (tgt_charges, tgt_balance, target_folio_id))

        audit_service.log_event(
            tenant_id="default-tenant",
            property_id=None,
            user_id=user_id,
            user_role="FrontDesk",
            action="SPLIT_FOLIO_ITEM",
            entity_type="FolioItem",
            entity_id=item_id,
            payload={
                "source_folio_id": source_folio_id,
                "target_folio_id": target_folio_id,
                "amount": item_cost
            }
        )

        return {
            "success": True,
            "item_id": item_id,
            "source_folio_id": source_folio_id,
            "target_folio_id": target_folio_id,
            "amount_transferred": item_cost
        }

    @classmethod
    def process_payment(
        cls,
        folio_id: str,
        amount: float,
        card_token: str,
        card_brand: str,
        card_last4: str,
        transaction_type: str = "CAPTURE",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes payment transaction against folio, updates balance, and logs payment."""
        with get_db() as db:
            folio = db.execute("SELECT * FROM folios WHERE id = ?", (folio_id,)).fetchone()
            if not folio:
                raise ValueError("Folio not found.")

            if transaction_type == "PRE_AUTH":
                res = payment_bridge.pre_authorize(card_token, amount, folio_id=folio_id)
            else:
                auth_code = f"AUTH-{uuid.uuid4().hex[:6].upper()}"
                res = payment_bridge.capture_settlement(card_token, auth_code, amount)

            txn_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO payment_transactions (
                    id, folio_id, transaction_type, amount, currency, gateway_token,
                    card_brand, card_last4, auth_code, status, gateway_response
                ) VALUES (?, ?, ?, ?, 'USD', ?, ?, ?, ?, 'SUCCESS', ?)
                """,
                (
                    txn_id, folio_id, transaction_type, amount,
                    card_token, card_brand, card_last4, res["auth_code"], res["message"]
                )
            )

            if transaction_type == "CAPTURE":
                new_payments = round(folio["total_payments"] + amount, 2)
                new_balance = round(folio["total_charges"] - new_payments, 2)
                new_status = "SETTLED" if new_balance <= 0.01 else "OPEN"
                db.execute(
                    """
                    UPDATE folios
                    SET total_payments = ?, balance = ?, status = ?
                    WHERE id = ?
                    """,
                    (new_payments, new_balance, new_status, folio_id)
                )
            else:
                new_balance = folio["balance"]

        return {
            "transaction_id": txn_id,
            "folio_id": folio_id,
            "amount": amount,
            "type": transaction_type,
            "auth_code": res["auth_code"],
            "current_balance": new_balance,
            "status": "APPROVED"
        }

    @classmethod
    def get_reservation_folios(cls, reservation_id: str) -> List[Dict[str, Any]]:
        """Fetches all split folios and their breakdown items for a reservation."""
        with get_db() as db:
            folios = db.execute(
                "SELECT * FROM folios WHERE reservation_id = ? ORDER BY folio_type ASC",
                (reservation_id,)
            ).fetchall()
            
            result = []
            for f in folios:
                f_dict = dict(f)
                items = db.execute(
                    "SELECT * FROM folio_items WHERE folio_id = ? ORDER BY posted_at ASC",
                    (f["id"],)
                ).fetchall()
                f_dict["items"] = [dict(item) for item in items]
                
                payments = db.execute(
                    "SELECT * FROM payment_transactions WHERE folio_id = ? ORDER BY created_at ASC",
                    (f["id"],)
                ).fetchall()
                f_dict["payments"] = [dict(p) for p in payments]
                result.append(f_dict)
            return result

folio_service = FolioService()

