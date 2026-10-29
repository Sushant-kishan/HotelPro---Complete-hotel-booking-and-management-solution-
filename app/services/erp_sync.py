"""
HotelPro ERP & Accounting Integration Service
PRD Section 6: Automated end-of-day journal and revenue sync with major ERP
and accounting software (QuickBooks, NetSuite, SAP).
"""
import json
from typing import Dict, Any, List
from app.database import get_db

class ERPAccountingBridge:
    @classmethod
    def export_journal_netsuite(cls, audit_record_id: str) -> str:
        """Formats night audit ledger record into NetSuite CSV Journal import format."""
        with get_db() as db:
            record = db.execute("SELECT * FROM night_audit_records WHERE id = ?", (audit_record_id,)).fetchone()
            if not record:
                raise ValueError("Night audit record not found.")

            journal = json.loads(record["erp_journal_payload"])
            lines = ["TranId,Date,Account,Debit,Credit,Memo"]
            date_str = journal["business_date"]
            tran_id = journal["journal_id"]

            for entry in journal["entries"]:
                debit = f"{entry['amount']:.2f}" if entry["type"] == "DEBIT" else ""
                credit = f"{entry['amount']:.2f}" if entry["type"] == "CREDIT" else ""
                lines.append(f"{tran_id},{date_str},\"{entry['account']}\",{debit},{credit},EOD Night Audit Reconciliation")

            csv_content = "\n".join(lines)
            db.execute("UPDATE night_audit_records SET erp_sync_status = 'SYNCED_NETSUITE' WHERE id = ?", (audit_record_id,))
            return csv_content

    @classmethod
    def export_journal_quickbooks(cls, audit_record_id: str) -> str:
        """Formats record into QuickBooks standard IIF journal format."""
        with get_db() as db:
            record = db.execute("SELECT * FROM night_audit_records WHERE id = ?", (audit_record_id,)).fetchone()
            if not record:
                raise ValueError("Night audit record not found.")

            journal = json.loads(record["erp_journal_payload"])
            lines = ["!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tDOCNUM\tMEMO"]
            lines.append("!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tDOCNUM\tMEMO")
            lines.append("!ENDTRNS")

            date_str = journal["business_date"]
            doc_num = journal["journal_id"]
            
            first = True
            for entry in journal["entries"]:
                tag = "TRNS" if first else "SPL"
                amt = entry["amount"] if entry["type"] == "DEBIT" else -entry["amount"]
                lines.append(f"{tag}\tGENERAL JOURNAL\t{date_str}\t{entry['account']}\t{amt:.2f}\t{doc_num}\tNight Audit Revenue Sync")
                first = False
            lines.append("ENDTRNS")

            db.execute("UPDATE night_audit_records SET erp_sync_status = 'SYNCED_QUICKBOOKS' WHERE id = ?", (audit_record_id,))
            return "\n".join(lines)

erp_bridge = ERPAccountingBridge()

