"""sp_booking.py
SP Appointment Booking MCP tools (Thin Slice - Booking Steps Only) - Customer-first.

This version simplifies booking by using a customer-first data model.

Data model
---------
- customers.json (REQUIRED) is the source of truth.
  - Look up customer by customer_id
  - Customer contains a list of policies (policy_id + policy_number + eligibility flags)
  - Customer contains a life_assured list (and policies can reference life_assured_ids)

Booking flow steps implemented
----------------------------
1. Identify policy holder or life assured
2. Identify customer location (user selects from hard-coded Hong Kong districts)
3. Identify specialty (mock list returned by tool)
4. Allow date and timeslot selection (fixed times)
5. Confirm appointment (summary)
6. If yes, save appointment (persisted)
7. If no, allowed edit options (Patient, Specialty, Date, Time)
8. Repeat to step 6

Notes
-----
- Location MUST be selected (locationId required in draft validation).
- specialties.json is OPTIONAL; falls back to in-code MOCK_SPECIALTIES.
- Confirmed appointments are persisted to DATA_DIR/appointments.json.

Recommended usage
-----------------
    from mcp.server.fastmcp import FastMCP
    from tools.sp_booking_steps import register_sp_booking_tools

    mcp = FastMCP("PHKL MCP", json_response=True)
    register_sp_booking_tools(mcp)

Environment

-----------
- Set PHKL_MCP_DATA_DIR to override fixture directory.

"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ------------------------------
# Configuration
# ------------------------------

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "mcp_mock_data"
DATA_DIR = Path(os.getenv("PHKL_MCP_DATA_DIR", str(DEFAULT_DATA_DIR)))

CUSTOMERS_FILE = "customers.json"
APPOINTMENTS_FILE = "appointments.json"

# Hard-coded Hong Kong districts (18 Districts)
HK_DISTRICTS: List[Dict[str, str]] = [
    {"location_id": "HK-CW", "display_name": "Central and Western"},
    {"location_id": "HK-EA", "display_name": "Eastern"},
    {"location_id": "HK-SO", "display_name": "Southern"},
    {"location_id": "HK-WC", "display_name": "Wan Chai"},
    {"location_id": "KL-KC", "display_name": "Kowloon City"},
    {"location_id": "KL-KT", "display_name": "Kwun Tong"},
    {"location_id": "KL-SSP", "display_name": "Sham Shui Po"},
    {"location_id": "KL-WTS", "display_name": "Wong Tai Sin"},
    {"location_id": "KL-YT", "display_name": "Yau Tsim Mong"},
    {"location_id": "NT-IS", "display_name": "Islands"},
    {"location_id": "NT-KN", "display_name": "Kwai Tsing"},
    {"location_id": "NT-N", "display_name": "North"},
    {"location_id": "NT-SK", "display_name": "Sai Kung"},
    {"location_id": "NT-ST", "display_name": "Sha Tin"},
    {"location_id": "NT-TM", "display_name": "Tuen Mun"},
    {"location_id": "NT-TW", "display_name": "Tsuen Wan"},
    {"location_id": "NT-TKP", "display_name": "Tai Po"},
    {"location_id": "NT-YL", "display_name": "Yuen Long"},
]

# Fixed time slots (no availability logic)
SLOT_WINDOWS = [
    {"slot_id": "SLOT-1000", "time": "10:00"},
    {"slot_id": "SLOT-1400", "time": "14:00"},
    {"slot_id": "SLOT-1600", "time": "16:00"},
]

# Mock specialties returned if specialties.json is absent.
MOCK_SPECIALTIES: List[Dict[str, Any]] = [
    {"specialty_id": "SP-CARD", "display_name": "Cardiology"},
    {"specialty_id": "SP-DERM", "display_name": "Dermatology"},
    {"specialty_id": "SP-ENT", "display_name": "ENT (Ear, Nose & Throat)"},
    {"specialty_id": "SP-GAST", "display_name": "Gastroenterology"},
    {"specialty_id": "SP-ORTH", "display_name": "Orthopedics"},
    {"specialty_id": "SP-OBGYN", "display_name": "Obstetrics & Gynecology"},
    {"specialty_id": "SP-OPH", "display_name": "Ophthalmology"},
    {"specialty_id": "SP-NEUR", "display_name": "Neurology"},
    {"specialty_id": "SP-PSYC", "display_name": "Psychiatry"},
    {"specialty_id": "SP-UROL", "display_name": "Urology"},
]

ALLOWED_EDIT_OPTIONS = ["Patient", "Specialty", "Date", "Time"]

# ------------------------------
# Helpers
# ------------------------------

def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(name: str, default: Any = None, *, required: bool = True) -> Any:
    _ensure_data_dir()
    path = DATA_DIR / name
    if not path.exists():
        if not required:
            return default
        raise FileNotFoundError(
            f"Missing mock data file: {path}. Set PHKL_MCP_DATA_DIR or place fixtures under ./mcp_mock_data"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(name: str, payload: Any) -> None:
    _ensure_data_dir()
    target = DATA_DIR / name
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _get_customer(customers: List[Dict[str, Any]], customer_id: str) -> Optional[Dict[str, Any]]:
    return next((c for c in customers if c.get("customer_id") == customer_id), None)


def _get_policy(customer: Dict[str, Any], policy_id: str) -> Optional[Dict[str, Any]]:
    return next((p for p in (customer.get("policies") or []) if p.get("policy_id") == policy_id), None)


def _policy_exists(customer: Dict[str, Any], policy_id: str) -> bool:
    return _get_policy(customer, policy_id) is not None


def _life_assured_exists(customer: Dict[str, Any], la_id: str) -> bool:
    return any(la_id == la.get("la_id") for la in (customer.get("life_assured") or []))


def _location_exists(location_id: str) -> bool:
    return any(location_id == d.get("location_id") for d in HK_DISTRICTS)


def _resolve_location(location_id: str) -> Optional[Dict[str, str]]:
    return next((d for d in HK_DISTRICTS if d.get("location_id") == location_id), None)


def _find_specialty(specialties: List[Dict[str, Any]], specialty_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in specialties if s.get("specialty_id") == specialty_id), None)

# ------------------------------
# MCP registration
# ------------------------------


def _register_sp_booking_tools(mcp, *, datasets: Optional[Dict[str, Any]] = None) -> None:
    """Register booking-step tools on an existing FastMCP instance."""

    data = datasets or {}

    customers = data.get("customers") or _load_json(CUSTOMERS_FILE, required=True)
    specialties = (
        data.get("specialties")
        or _load_json("specialties.json", default=MOCK_SPECIALTIES, required=False)
        or MOCK_SPECIALTIES
    )

    # --------------------------
    # Step 1: Customer -> policy -> patient
    # --------------------------

    @mcp.tool()
    def sp_getCustomer(customerId: str) -> Dict[str, Any]:
        """Lookup customer by customerId."""
        cust = _get_customer(customers, customerId)
        return {
            "customerId": customerId,
            "found": cust is not None,
            "customer": cust,
        }

    @mcp.tool()
    def sp_listPolicies(customerId: str) -> Dict[str, Any]:
        """List policies under a customer (for selection)."""
        cust = _get_customer(customers, customerId)
        if not cust:
            return {"customerId": customerId, "error": "CUSTOMER_NOT_FOUND", "policies": []}

        items = [
            {
                "policy_id": p.get("policy_id"),
                "policy_number": p.get("policy_number"),
                "policy_number_masked": p.get("policy_number_masked"),
                "direct_billing": bool(p.get("direct_billing")),
                "h2p_eligible": bool(p.get("h2p_eligible")),
            }
            for p in (cust.get("policies") or [])
        ]
        return {"customerId": customerId, "policies": items, "count": len(items)}

    @mcp.tool()
    def sp_listLifeAssured(customerId: str) -> Dict[str, Any]:
        """List life assured options under a customer (for patient selection)."""
        cust = _get_customer(customers, customerId)
        if not cust:
            return {"customerId": customerId, "error": "CUSTOMER_NOT_FOUND", "lifeAssured": []}
        return {"customerId": customerId, "lifeAssured": cust.get("life_assured") or [], "count": len(cust.get("life_assured") or [])}

    @mcp.tool()
    def sp_checkEligibility(customerId: str, policyId: str) -> Dict[str, Any]:
        """Eligibility check for a specific customer policy.

        This is simpler than a global scan: select policy first, then check if it is eligible.
        """
        cust = _get_customer(customers, customerId)
        if not cust:
            return {"eligible": False, "error": "CUSTOMER_NOT_FOUND"}

        pol = _get_policy(cust, policyId)
        if not pol:
            return {"eligible": False, "error": "POLICY_NOT_FOUND"}

        eligible = bool(pol.get("direct_billing")) and bool(pol.get("h2p_eligible"))
        return {
            "customerId": customerId,
            "policyId": policyId,
            "eligible": eligible,
            "reasons": [] if eligible else ["NOT_ELIGIBLE"],
            "policy": {
                "policy_id": pol.get("policy_id"),
                "policy_number_masked": pol.get("policy_number_masked"),
                "direct_billing": bool(pol.get("direct_billing")),
                "h2p_eligible": bool(pol.get("h2p_eligible")),
            },
        }

    # --------------------------
    # Step 2: Location selection
    # --------------------------

    @mcp.tool()
    def sp_listLocations() -> Dict[str, Any]:
        """Return HK district locations."""
        return {"locations": HK_DISTRICTS, "count": len(HK_DISTRICTS)}

    # --------------------------
    # Step 3: Specialty selection
    # --------------------------

    @mcp.tool()
    def sp_listSpecialties() -> Dict[str, Any]:
        """Return mock specialties for display."""
        return {"specialties": specialties, "count": len(specialties)}

    # --------------------------
    # Step 4: Date/time selection
    # --------------------------

    @mcp.tool()
    def sp_getSlotWindows() -> Dict[str, Any]:
        """Return fixed slot windows."""
        return {"slotWindows": SLOT_WINDOWS}

    @mcp.tool()
    def sp_getTodaysDate() -> Dict[str, str]:
        """Return today's date in ISO 8601 format (YYYY-MM-DD). 
        This is useful for calculating relative dates like 'tomorrow'."""
        return {"today": date.today().isoformat()}

    @mcp.tool()
    def sp_validateAppointmentDraft(draft: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize a booking draft.

        Required:
        - customerId
        - policyId
        - forWhom: self | life_assured
        - locationId
        - specialtyId
        - appointmentDate (YYYY-MM-DD)
        - slotId

        Optional:
        - lifeAssuredId (required if forWhom=life_assured)
        """

        errors: List[Dict[str, Any]] = []
        missing: List[str] = []

        def req(field: str) -> None:
            if not draft.get(field):
                missing.append(field)

        req("customerId")
        req("policyId")
        req("forWhom")
        req("locationId")
        req("specialtyId")
        req("appointmentDate")
        req("slotId")

        customer = _get_customer(customers, draft.get("customerId")) if draft.get("customerId") else None
        if draft.get("customerId") and not customer:
            errors.append({"field": "customerId", "code": "CUSTOMER_NOT_FOUND"})

        if customer and draft.get("policyId") and not _policy_exists(customer, draft.get("policyId")):
            errors.append({"field": "policyId", "code": "POLICY_NOT_FOUND"})

        for_whom = (draft.get("forWhom") or "").lower().strip() or None
        if for_whom and for_whom not in {"self", "life_assured"}:
            errors.append({"field": "forWhom", "code": "INVALID_VALUE", "message": "forWhom must be self or life_assured"})

        if for_whom == "life_assured" and not draft.get("lifeAssuredId"):
            missing.append("lifeAssuredId")
        if for_whom == "life_assured" and customer and draft.get("lifeAssuredId") and not _life_assured_exists(customer, draft.get("lifeAssuredId")):
            errors.append({"field": "lifeAssuredId", "code": "LIFE_ASSURED_NOT_FOUND"})

        if draft.get("locationId") and not _location_exists(draft.get("locationId")):
            errors.append({"field": "locationId", "code": "UNKNOWN_LOCATION"})

        if draft.get("specialtyId") and not _find_specialty(specialties, draft.get("specialtyId")):
            errors.append({"field": "specialtyId", "code": "UNKNOWN_SPECIALTY"})

        # Date must be >= tomorrow
        earliest_allowed = date.today() + timedelta(days=1)
        appt_date_raw = draft.get("appointmentDate")
        appt_date: Optional[date] = None
        if appt_date_raw:
            try:
                appt_date = date.fromisoformat(appt_date_raw)
                if appt_date < earliest_allowed:
                    errors.append({"field": "appointmentDate", "code": "DATE_TOO_EARLY", "message": f"appointmentDate must be {earliest_allowed.isoformat()} or later"})
            except Exception:
                errors.append({"field": "appointmentDate", "code": "INVALID_DATE"})

        allowed_slot_ids = {s["slot_id"] for s in SLOT_WINDOWS}
        slot_id = draft.get("slotId")
        if slot_id and slot_id not in allowed_slot_ids:
            errors.append({"field": "slotId", "code": "INVALID_SLOT"})

        normalized = dict(draft)
        normalized["forWhom"] = for_whom
        if normalized.get("locationId"):
            normalized["location"] = _resolve_location(normalized["locationId"])
        if appt_date:
            normalized["appointmentDate"] = appt_date.isoformat()
        if slot_id in allowed_slot_ids:
            normalized["appointmentTime"] = next((s["time"] for s in SLOT_WINDOWS if s["slot_id"] == slot_id), None)

        return {
            "isValid": len(errors) == 0 and len(missing) == 0,
            "missingFields": sorted(set(missing)),
            "errors": errors,
            "normalizedDraft": normalized,
        }

    # --------------------------
    # Step 5: Confirmation summary
    # --------------------------

    @mcp.tool()
    def sp_buildConfirmationSummary(draft: Dict[str, Any]) -> Dict[str, Any]:
        """Build a confirmation summary from a validated draft."""
        specialty = _find_specialty(specialties, draft.get("specialtyId", "")) if draft else None
        summary = {
            "customerId": draft.get("customerId"),
            "policyId": draft.get("policyId"),
            "patient": {"forWhom": draft.get("forWhom"), "lifeAssuredId": draft.get("lifeAssuredId")},
            "location": draft.get("location"),
            "specialty": {
                "specialtyId": draft.get("specialtyId"),
                "displayName": (specialty or {}).get("display_name"),
            },
            "appointment": {"date": draft.get("appointmentDate"), "time": draft.get("appointmentTime"), "slotId": draft.get("slotId")},
        }
        return {"summary": summary}

    # --------------------------
    # Step 6: Save confirmed appointment (persist)
    # --------------------------

    @mcp.tool()
    def sp_saveConfirmedAppointment(confirmedDraft: Dict[str, Any], idempotencyKey: Optional[str] = None) -> Dict[str, Any]:
        """Persist a confirmed appointment and return appointmentId."""
        validation = sp_validateAppointmentDraft(confirmedDraft)
        if not validation.get("isValid"):
            return {"status": "FAILED", "error": "INVALID_DRAFT", "validation": validation}

        draft = validation["normalizedDraft"]
        db = _load_json(APPOINTMENTS_FILE, default={"appointments": [], "idempotency": {}}, required=False)
        appointments: List[Dict[str, Any]] = db.get("appointments", [])
        idem_map: Dict[str, str] = db.get("idempotency", {})

        if idempotencyKey:
            existing_id = idem_map.get(idempotencyKey)
            if existing_id:
                existing = next((a for a in appointments if a.get("appointment_id") == existing_id), None)
                if existing:
                    return {"status": "DUPLICATE", "appointmentId": existing_id, "appointment": existing}

        customer = _get_customer(customers, draft.get("customerId"))
        policy = _get_policy(customer, draft.get("policyId")) if customer else None
        specialty = _find_specialty(specialties, draft.get("specialtyId", "")) or {}

        appointment_id = f"APT-{uuid.uuid4().hex[:10].upper()}"
        record = {
            "appointment_id": appointment_id,
            "created_at": _utc_now_iso(),
            "status": "CONFIRMED",
            "customerId": draft.get("customerId"),
            "policyId": draft.get("policyId"),
            "policyNumberMasked": (policy or {}).get("policy_number_masked"),
            "forWhom": draft.get("forWhom"),
            "lifeAssuredId": draft.get("lifeAssuredId"),
            "locationId": draft.get("locationId"),
            "location": draft.get("location"),
            "specialtyId": draft.get("specialtyId"),
            "specialtyName": specialty.get("display_name"),
            "appointment_date": draft.get("appointmentDate"),
            "time_slot": draft.get("appointmentTime"),
            "slot_id": draft.get("slotId"),
        }

        appointments.append(record)
        if idempotencyKey:
            idem_map[idempotencyKey] = appointment_id

        db["appointments"] = appointments
        db["idempotency"] = idem_map
        _write_json_atomic(APPOINTMENTS_FILE, db)

        return {"status": "CONFIRMED", "appointmentId": appointment_id, "appointment": record}

    # --------------------------
    # Step 7: Edit options
    # --------------------------

    @mcp.tool()
    def sp_getAllowedEditOptions() -> Dict[str, Any]:
        return {"allowedEditOptions": ALLOWED_EDIT_OPTIONS}

    # Optional helper
    @mcp.tool()
    def sp_getAppointmentById(appointmentId: str) -> Dict[str, Any]:
        db = _load_json(APPOINTMENTS_FILE, default={"appointments": []}, required=False)
        appointments: List[Dict[str, Any]] = db.get("appointments", [])
        rec = next((a for a in appointments if a.get("appointment_id") == appointmentId), None)
        return {"found": rec is not None, "appointment": rec}
