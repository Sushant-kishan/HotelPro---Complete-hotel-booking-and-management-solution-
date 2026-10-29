"""
HotelPro Role-Based Access Control (RBAC) Module
Granular permissions partitioned across strict roles per PRD Section 4.1:
SuperAdmin, PropertyManager, FrontDesk, Housekeeping, Auditor.
"""
from enum import Enum
from typing import Set, Dict

class Role(str, Enum):
    SUPER_ADMIN = "SuperAdmin"
    PROPERTY_MANAGER = "PropertyManager"
    FRONT_DESK = "FrontDesk"
    HOUSEKEEPING = "Housekeeping"
    AUDITOR = "Auditor"
    GUEST = "Guest"

class Permission(str, Enum):
    # System & Multi-tenant administration
    MANAGE_TENANTS = "manage_tenants"
    MANAGE_PROPERTIES = "manage_properties"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    
    # Inventory & Dynamic Rates
    MANAGE_INVENTORY = "manage_inventory"
    VIEW_INVENTORY = "view_inventory"
    CONFIGURE_RATES = "configure_rates"
    
    # Reservations & Bookings
    CREATE_RESERVATION = "create_reservation"
    VIEW_RESERVATIONS = "view_reservations"
    MODIFY_RESERVATION = "modify_reservation"
    CANCEL_RESERVATION = "cancel_reservation"
    
    # Front-Desk Operations (< 60s check-in/out)
    CHECK_IN_GUEST = "check_in_guest"
    CHECK_OUT_GUEST = "check_out_guest"
    ENCODE_KEYCARD = "encode_keycard"
    ALLOCATE_ROOM = "allocate_room"
    
    # Housekeeping
    VIEW_HOUSEKEEPING = "view_housekeeping"
    UPDATE_ROOM_CLEANLINESS = "update_room_cleanliness"
    ASSIGN_CLEANING_TASK = "assign_cleaning_task"
    
    # Folio & Billing
    VIEW_FOLIO = "view_folio"
    POST_INCIDENTAL = "post_incidental"
    SPLIT_FOLIO = "split_folio"
    PROCESS_PAYMENT = "process_payment"
    
    # Night Audit & ERP
    EXECUTE_NIGHT_AUDIT = "execute_night_audit"
    VIEW_FINANCIAL_REPORTS = "view_financial_reports"
    SYNC_ERP_JOURNAL = "sync_erp_journal"
    
    # PII & GDPR
    VIEW_PII = "view_pii"
    EXPORT_GDPR = "export_gdpr"
    ERASE_GDPR = "erase_gdpr"

# Granular Permission Mapping by Role
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.SUPER_ADMIN: {p for p in Permission},
    
    Role.PROPERTY_MANAGER: {
        Permission.MANAGE_PROPERTIES,
        Permission.MANAGE_USERS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.MANAGE_INVENTORY,
        Permission.VIEW_INVENTORY,
        Permission.CONFIGURE_RATES,
        Permission.CREATE_RESERVATION,
        Permission.VIEW_RESERVATIONS,
        Permission.MODIFY_RESERVATION,
        Permission.CANCEL_RESERVATION,
        Permission.CHECK_IN_GUEST,
        Permission.CHECK_OUT_GUEST,
        Permission.ENCODE_KEYCARD,
        Permission.ALLOCATE_ROOM,
        Permission.VIEW_HOUSEKEEPING,
        Permission.UPDATE_ROOM_CLEANLINESS,
        Permission.ASSIGN_CLEANING_TASK,
        Permission.VIEW_FOLIO,
        Permission.POST_INCIDENTAL,
        Permission.SPLIT_FOLIO,
        Permission.PROCESS_PAYMENT,
        Permission.EXECUTE_NIGHT_AUDIT,
        Permission.VIEW_FINANCIAL_REPORTS,
        Permission.SYNC_ERP_JOURNAL,
        Permission.VIEW_PII,
        Permission.EXPORT_GDPR,
        Permission.ERASE_GDPR,
    },
    
    Role.FRONT_DESK: {
        Permission.VIEW_INVENTORY,
        Permission.CREATE_RESERVATION,
        Permission.VIEW_RESERVATIONS,
        Permission.MODIFY_RESERVATION,
        Permission.CANCEL_RESERVATION,
        Permission.CHECK_IN_GUEST,
        Permission.CHECK_OUT_GUEST,
        Permission.ENCODE_KEYCARD,
        Permission.ALLOCATE_ROOM,
        Permission.VIEW_HOUSEKEEPING,
        Permission.VIEW_FOLIO,
        Permission.POST_INCIDENTAL,
        Permission.SPLIT_FOLIO,
        Permission.PROCESS_PAYMENT,
        Permission.VIEW_PII,
    },
    
    Role.HOUSEKEEPING: {
        Permission.VIEW_HOUSEKEEPING,
        Permission.UPDATE_ROOM_CLEANLINESS,
        Permission.VIEW_INVENTORY,
    },
    
    Role.AUDITOR: {
        Permission.VIEW_INVENTORY,
        Permission.VIEW_RESERVATIONS,
        Permission.VIEW_FOLIO,
        Permission.EXECUTE_NIGHT_AUDIT,
        Permission.VIEW_FINANCIAL_REPORTS,
        Permission.SYNC_ERP_JOURNAL,
        Permission.VIEW_AUDIT_LOGS,
    },
    
    Role.GUEST: {
        Permission.VIEW_INVENTORY,
        Permission.CREATE_RESERVATION,
        Permission.VIEW_FOLIO,
    }
}

def has_permission(role_str: str, required_permission: Permission) -> bool:
    """Verifies whether a given role holds the required capability."""
    try:
        role = Role(role_str)
        allowed = ROLE_PERMISSIONS.get(role, set())
        return required_permission in allowed
    except ValueError:
        return False

