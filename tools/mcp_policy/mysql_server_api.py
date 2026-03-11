# prudential_mysql_server_api.py
#!/usr/bin/env python3
"""
    run: python prudential_mysql_server_api.py, to start mcp mysql http server
"""
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any, List
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Dict
from mcp import types as mcp_types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).parent / "booking_data"
DATA_DIR = Path('mcp_policy', str(DEFAULT_DATA_DIR))
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


def _ensure_data_dir() -> None:
    """Ensure data directory exists"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def _load_json(filename: str, default: Any = None) -> Any:
    """Load JSON file"""
    _ensure_data_dir()
    path = DATA_DIR / filename
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"Missing data file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def _write_json_atomic(filename: str, payload: Any) -> None:
    """Atomically write JSON file"""
    _ensure_data_dir()
    target = DATA_DIR / filename
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)

def _utc_now_iso() -> str:
    """Get current UTC time in ISO format"""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def _normalize_text(s: Optional[str]) -> str:
    """Normalize text for search"""
    return (s or "").strip().lower()

def _safe_int(s: Optional[str], default: int = 0) -> int:
    """Safely convert string to int"""
    try:
        return int(s) if s is not None else default
    except Exception:
        return default

def _paginate(items: List[Dict[str, Any]], page_token: Optional[str], limit: int) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Paginate a list of items"""
    offset = _safe_int(page_token, 0)
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = items[offset: offset + limit]
    next_offset = offset + limit
    next_token = str(next_offset) if next_offset < len(items) else None
    return page, next_token

def _match_fuzzy(needle: str, hay: str) -> bool:
    """Lightweight fuzzy matching: substring + token overlap."""
    needle = _normalize_text(needle)
    hay = _normalize_text(hay)
    if not needle:
        return True
    if needle in hay:
        return True
    n_tokens = set(re.split(r"\W+", needle)) - {""}
    h_tokens = set(re.split(r"\W+", hay)) - {""}
    return len(n_tokens & h_tokens) > 0


# Policy methods
def get_user_policy_and_products(client_id_list: List[str]) -> List:
    """
    use the client_id to retreive the policy and products list

    Args:
        client_id: the client_id list to get finnal data

    Returns:
        JSON format string with query results or execution status
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    mock_data_path = os.path.join(current_dir, 'mock_policy_data.json')
    with open(mock_data_path) as f:
        data = json.load(f)

    response = []
    for client_id in client_id_list:
        for entry in data:
            if client_id == entry.get('client_id'):
                # entry.pop('client_id', '')
                response.append(entry)
                break

    return json.dumps(response, ensure_ascii=False, indent=2)


def get_user_client_id_list(user_id: str='test_123') -> str:
    """
        use the user_id to retreive client_id list

        Args:
            user_id: the user_id to get finnal data

        Returns:
            JSON format string with query results or execution status
    """

    current_dir = os.path.dirname(os.path.abspath(__file__))
    mock_data_path = os.path.join(current_dir, 'mock_user_client_id.json')
    with open(mock_data_path) as f:
        data = json.load(f)

    response = []
    print(111, user_id)
    for entry in data:
        if user_id == entry.get('user_id'):
            # entry.pop('client_id', '')
            response.extend(entry.get('client_id'))
            break
    print(222, response)
    return json.dumps(response, ensure_ascii=False, indent=2)


def _get_customer(customer_id: str) -> Optional[Dict[str, Any]]:
    """Get customer information by ID"""
    data = _load_json('customer_data.json', default={})
    customers = data.get('customers', [])
    return next((c for c in customers if c.get('customer_id') == customer_id), None)

def _get_policy(customer: Dict[str, Any], policy_id: str) -> Optional[Dict[str, Any]]:
    """Get policy information from customer data"""
    return next((p for p in (customer.get('policies') or []) if p.get('policy_id') == policy_id), None)

def _policy_exists(customer: Dict[str, Any], policy_id: str) -> bool:
    """Check if policy exists for customer"""
    return _get_policy(customer, policy_id) is not None

def _life_assured_exists(customer: Dict[str, Any], la_id: str) -> bool:
    """Check if life assured person exists for customer"""
    return any(la_id == la.get('la_id') for la in (customer.get('life_assured') or []))

def _get_locations() -> List[Dict[str, str]]:
    """Get list of Hong Kong districts"""
    data = _load_json('customer_data.json', default={})
    return data.get('locations', [])

def _location_exists(location_id: str) -> bool:
    """Check if location exists"""
    locations = _get_locations()
    return any(location_id == d.get('location_id') for d in locations)

def _resolve_location(location_id: str) -> Optional[Dict[str, str]]:
    """Get location details by ID"""
    locations = _get_locations()
    return next((d for d in locations if d.get('location_id') == location_id), None)

def _get_specialties() -> List[Dict[str, Any]]:
    """Get list of medical specialties"""
    data = _load_json('customer_data.json', default={})
    return data.get('specialties', [])

def _find_specialty(specialty_id: str) -> Optional[Dict[str, Any]]:
    """Find specialty by ID"""
    specialties = _get_specialties()
    return next((s for s in specialties if s.get('specialty_id') == specialty_id), None)

def _get_slot_windows() -> List[Dict[str, str]]:
    """Get list of available time slots"""
    data = _load_json('customer_data.json', default={})
    return data.get('slot_windows', [])

def sp_get_customer(customer_id: str) -> str:
    """Lookup customer by customerId."""
    cust = _get_customer(customer_id)
    result = {
        "customerId": customer_id,
        "found": cust is not None,
        "customer": cust,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_list_policies(customer_id: str) -> str:
    """List policies under a customer (for selection)."""
    cust = _get_customer(customer_id)
    if not cust:
        result = {"customerId": customer_id, "error": "CUSTOMER_NOT_FOUND", "policies": []}
        return json.dumps(result, ensure_ascii=False, indent=2)

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
    result = {"customerId": customer_id, "policies": items, "count": len(items)}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_list_life_assured(customer_id: str) -> str:
    """List life assured options under a customer (for patient selection)."""
    cust = _get_customer(customer_id)
    if not cust:
        result = {"customerId": customer_id, "error": "CUSTOMER_NOT_FOUND", "lifeAssured": []}
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    result = {
        "customerId": customer_id, 
        "lifeAssured": cust.get("life_assured") or [], 
        "count": len(cust.get("life_assured") or [])
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_check_eligibility(customer_id: str, policy_id: str) -> str:
    """Eligibility check for a specific customer policy."""
    cust = _get_customer(customer_id)
    if not cust:
        result = {"eligible": False, "error": "CUSTOMER_NOT_FOUND"}
        return json.dumps(result, ensure_ascii=False, indent=2)

    pol = _get_policy(cust, policy_id)
    if not pol:
        result = {"eligible": False, "error": "POLICY_NOT_FOUND"}
        return json.dumps(result, ensure_ascii=False, indent=2)

    eligible = bool(pol.get("direct_billing")) and bool(pol.get("h2p_eligible"))
    result = {
        "customerId": customer_id,
        "policyId": policy_id,
        "eligible": eligible,
        "reasons": [] if eligible else ["NOT_ELIGIBLE"],
        "policy": {
            "policy_id": pol.get("policy_id"),
            "policy_number_masked": pol.get("policy_number_masked"),
            "direct_billing": bool(pol.get("direct_billing")),
            "h2p_eligible": bool(pol.get("h2p_eligible")),
        },
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_list_locations() -> str:
    """Return HK district locations."""
    locations = _get_locations()
    result = {"locations": locations, "count": len(locations)}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_list_specialties() -> str:
    """Return mock specialties for display."""
    specialties = _get_specialties()
    result = {"specialties": specialties, "count": len(specialties)}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_get_slot_windows() -> str:
    """Return fixed slot windows."""
    slots = _get_slot_windows()
    result = {"slotWindows": slots}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_get_todays_date() -> str:
    """Return today's date in ISO 8601 format (YYYY-MM-DD)."""
    result = {"today": date.today().isoformat()}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_validate_appointment_draft(draft_json: str) -> str:
    """Validate and normalize a booking draft."""
    try:
        draft = json.loads(draft_json) if isinstance(draft_json, str) else draft_json
    except:
        result = {"isValid": False, "missingFields": [], "errors": [{"code": "INVALID_JSON"}]}
        return json.dumps(result, ensure_ascii=False, indent=2)

    errors = []
    missing = []

    def req(field: str) -> None:
        """Check if required field is present"""
        if not draft.get(field):
            missing.append(field)

    req("customerId")
    req("policyId")
    req("forWhom")
    req("locationId")
    req("specialtyId")
    req("appointmentDate")
    req("slotId")

    customer = _get_customer(draft.get("customerId")) if draft.get("customerId") else None
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

    if draft.get("specialtyId") and not _find_specialty(draft.get("specialtyId")):
        errors.append({"field": "specialtyId", "code": "UNKNOWN_SPECIALTY"})

    # Date must be >= tomorrow
    earliest_allowed = date.today() + timedelta(days=1)
    appt_date_raw = draft.get("appointmentDate")
    appt_date = None
    if appt_date_raw:
        try:
            appt_date = date.fromisoformat(appt_date_raw)
            if appt_date < earliest_allowed:
                errors.append({"field": "appointmentDate", "code": "DATE_TOO_EARLY", "message": f"appointmentDate must be {earliest_allowed.isoformat()} or later"})
        except Exception:
            errors.append({"field": "appointmentDate", "code": "INVALID_DATE"})

    allowed_slot_ids = {s["slot_id"] for s in _get_slot_windows()}
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
        slot_map = {s["slot_id"]: s["time"] for s in _get_slot_windows()}
        normalized["appointmentTime"] = slot_map.get(slot_id)

    result = {
        "isValid": len(errors) == 0 and len(missing) == 0,
        "missingFields": sorted(set(missing)),
        "errors": errors,
        "normalizedDraft": normalized,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_build_confirmation_summary(draft_json: str) -> str:
    """Build a confirmation summary from a validated draft."""
    try:
        draft = json.loads(draft_json) if isinstance(draft_json, str) else draft_json
    except:
        return json.dumps({"summary": {}}, ensure_ascii=False, indent=2)

    specialty = _find_specialty(draft.get("specialtyId", "")) if draft else None
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
    result = {"summary": summary}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_save_confirmed_appointment(confirmed_draft_json: str, idempotency_key: Optional[str] = None) -> str:
    """Persist a confirmed appointment and return appointmentId."""
    try:
        confirmed_draft = json.loads(confirmed_draft_json) if isinstance(confirmed_draft_json, str) else confirmed_draft_json
    except:
        result = {"status": "FAILED", "error": "INVALID_DRAFT"}
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Validate the draft
    validation = json.loads(sp_validate_appointment_draft(confirmed_draft))
    if not validation.get("isValid"):
        result = {"status": "FAILED", "error": "INVALID_DRAFT", "validation": validation}
        return json.dumps(result, ensure_ascii=False, indent=2)

    draft = validation["normalizedDraft"]
    data = _load_json('customer_data.json', default={"customers": [], "appointments": []})
    appointments = data.get("appointments", [])
    
    # Idempotency check
    if idempotency_key:
        existing = next((a for a in appointments if a.get("idempotency_key") == idempotency_key), None)
        if existing:
            result = {"status": "DUPLICATE", "appointmentId": existing.get("appointment_id"), "appointment": existing}
            return json.dumps(result, ensure_ascii=False, indent=2)

    customer = _get_customer(draft.get("customerId"))
    policy = _get_policy(customer, draft.get("policyId")) if customer else None
    specialty = _find_specialty(draft.get("specialtyId", "")) or {}

    appointment_id = f"APT-{uuid.uuid4().hex[:10].upper()}"
    record = {
        "appointment_id": appointment_id,
        "idempotency_key": idempotency_key,
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
    data["appointments"] = appointments
    _write_json_atomic('customer_data.json', data)

    result = {"status": "CONFIRMED", "appointmentId": appointment_id, "appointment": record}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_get_appointment_by_id(appointment_id: str) -> str:
    """Get appointment by ID."""
    data = _load_json('customer_data.json', default={"appointments": []})
    appointments = data.get("appointments", [])
    rec = next((a for a in appointments if a.get("appointment_id") == appointment_id), None)
    result = {"found": rec is not None, "appointment": rec}
    return json.dumps(result, ensure_ascii=False, indent=2)

def sp_get_allowed_edit_options() -> str:
    """Get allowed edit options."""
    options = ["Patient", "Specialty", "Date", "Time"]
    result = {"allowedEditOptions": options}
    return json.dumps(result, ensure_ascii=False, indent=2)


# ------------------------------
# Doctor Finder Functions
# ------------------------------

def _load_doctor_data():
    """Load all doctor-related data"""
    districts = _load_json('districts.json', default=[])
    specialties = _load_json('specialties.json', default=[])
    providers = _load_json('providers.json', default=[])
    doctors = _load_json('doctors.json', default=[])
    return districts, specialties, providers, doctors

def doctor_finder_list_specialties() -> str:
    """Return all specialties (single source for UI selection)."""
    _, specialties, _, _ = _load_doctor_data()
    result = {"specialties": specialties}
    return json.dumps(result, ensure_ascii=False, indent=2)

def doctor_finder_list_districts() -> str:
    """Return all districts (single source for UI selection)."""
    districts, _, _, _ = _load_doctor_data()
    result = {"districts": districts}
    return json.dumps(result, ensure_ascii=False, indent=2)

def doctor_finder_search_providers(provider_free_text: str, limit: int = 10) -> str:
    """Search providers by free-text, returning matches for disambiguation."""
    _, _, providers, _ = _load_doctor_data()
    q = _normalize_text(provider_free_text)
    matches = [p for p in providers if _match_fuzzy(q, p.get("name", ""))]
    matches.sort(key=lambda x: (not bool(x.get("preferred")), x.get("name", "")))
    result = {
        "query": provider_free_text,
        "providers": matches[: max(1, min(limit, MAX_PAGE_SIZE))],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

def doctor_finder_get_doctor_details(doctor_id: str) -> str:
    """Fetch a single doctor record by ID."""
    _, _, providers, doctors = _load_doctor_data()
    doctor = next((d for d in doctors if d.get("doctor_id") == doctor_id), None)
    provider = None
    if doctor:
        provider = next((p for p in providers if p.get("provider_id") == doctor.get("provider_id")), None)
    result = {"doctor": doctor, "provider": provider}
    if not doctor:
        result["error"] = "DOCTOR_NOT_FOUND"
    return json.dumps(result, ensure_ascii=False, indent=2)

def doctor_finder_search(
    specialty_id: str,
    district_id: Optional[str] = None,
    gender: Optional[str] = None,
    doctor_name: Optional[str] = None,
    provider_name: Optional[str] = None,
    provider_id: Optional[str] = None,
    limit: int = DEFAULT_PAGE_SIZE,
    page_token: Optional[str] = None,
) -> str:
    """Search panel doctors by filters.

    Rules supported:
    - Specialty is mandatory.
    - District and gender are optional (None means "No preference").
    - Doctor name/provider name can be used for free-text narrowing.
    - Preferred providers first.
    - Pagination via page_token/limit.
    """
    _, _, _, doctors = _load_doctor_data()
    
    if not specialty_id:
        result = {
            "error": "SPECIALTY_REQUIRED", 
            "doctors": [], 
            "count": 0, 
            "nextPageToken": None
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    dn = _normalize_text(doctor_name)
    pn = _normalize_text(provider_name)

    results = []
    for d in doctors:
        if d.get("specialty_id") != specialty_id:
            continue
        if district_id and d.get("district_id") != district_id:
            continue
        if gender and d.get("gender") != gender:
            continue
        if provider_id and d.get("provider_id") != provider_id:
            continue
        if dn and not _match_fuzzy(dn, d.get("name", "")):
            continue
        if pn and not _match_fuzzy(pn, d.get("provider_name", "")):
            continue
        results.append(d)

    results.sort(key=lambda x: (not bool(x.get("preferred")), x.get("name", "")))
    page, next_token = _paginate(results, page_token, limit)

    result = {
        "filters": {
            "specialtyId": specialty_id,
            "districtId": district_id,
            "gender": gender,
            "doctorName": doctor_name,
            "providerName": provider_name,
            "providerId": provider_id,
        },
        "count": len(results),
        "doctors": page,
        "nextPageToken": next_token,
        "noResults": len(results) == 0,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


GET_USER_POLICY_AND_PRODUCTS_SCHEMA = {
    "name": "get_user_policy_and_products",
    "description": "use the client_id list to retreive the user policy data, policy data also contains product details",
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "array",
                "description": "the client_id list to get the policy"
            }
        },
        "required": ["client_id"]
    }
}

GET_USER_CLIENT_ID_SCHEMA = {
    "name": "get_user_client_id_list",
    "description": "use the user_id to retreive the user client_id list data",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "the user_id to get the client_id list"
            }
        },
        "required": ["user_id"]
    }
}


# Booking tool schemas
SP_GET_CUSTOMER_SCHEMA = {
    "name": "sp_get_customer",
    "description": "Lookup customer by customerId",
    "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "the customer id to lookup"
            }
        },
        "required": ["customer_id"]
    }
}

SP_LIST_POLICIES_SCHEMA = {
    "name": "sp_list_policies",
    "description": "List policies under a customer (for selection)",
    "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "the customer id"
            }
        },
        "required": ["customer_id"]
    }
}

SP_LIST_LIFE_ASSURED_SCHEMA = {
    "name": "sp_list_life_assured",
    "description": "List life assured options under a customer (for patient selection)",
    "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "the customer id"
            }
        },
        "required": ["customer_id"]
    }
}

SP_CHECK_ELIGIBILITY_SCHEMA = {
    "name": "sp_check_eligibility",
    "description": "Eligibility check for a specific customer policy",
    "parameters": {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "the customer id"
            },
            "policy_id": {
                "type": "string",
                "description": "the policy id to check"
            }
        },
        "required": ["customer_id", "policy_id"]
    }
}

SP_LIST_LOCATIONS_SCHEMA = {
    "name": "sp_list_locations",
    "description": "Return HK district locations",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

SP_LIST_SPECIALTIES_SCHEMA = {
    "name": "sp_list_specialties",
    "description": "Return mock specialties for display",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

SP_GET_SLOT_WINDOWS_SCHEMA = {
    "name": "sp_get_slot_windows",
    "description": "Return fixed slot windows",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

SP_GET_TODAYS_DATE_SCHEMA = {
    "name": "sp_get_todays_date",
    "description": "Return today's date in ISO 8601 format (YYYY-MM-DD)",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

SP_VALIDATE_APPOINTMENT_DRAFT_SCHEMA = {
    "name": "sp_validate_appointment_draft",
    "description": "Validate and normalize a booking draft",
    "parameters": {
        "type": "object",
        "properties": {
            "draft": {
                "type": "object",
                "description": "the appointment draft to validate"
            }
        },
        "required": ["draft"]
    }
}

SP_BUILD_CONFIRMATION_SUMMARY_SCHEMA = {
    "name": "sp_build_confirmation_summary",
    "description": "Build a confirmation summary from a validated draft",
    "parameters": {
        "type": "object",
        "properties": {
            "draft": {
                "type": "object",
                "description": "the validated draft"
            }
        },
        "required": ["draft"]
    }
}

SP_SAVE_CONFIRMED_APPOINTMENT_SCHEMA = {
    "name": "sp_save_confirmed_appointment",
    "description": "Persist a confirmed appointment and return appointmentId",
    "parameters": {
        "type": "object",
        "properties": {
            "confirmed_draft": {
                "type": "object",
                "description": "the confirmed draft to save"
            },
            "idempotency_key": {
                "type": "string",
                "description": "optional idempotency key"
            }
        },
        "required": ["confirmed_draft"]
    }
}

SP_GET_APPOINTMENT_BY_ID_SCHEMA = {
    "name": "sp_get_appointment_by_id",
    "description": "Get appointment by ID",
    "parameters": {
        "type": "object",
        "properties": {
            "appointment_id": {
                "type": "string",
                "description": "the appointment id"
            }
        },
        "required": ["appointment_id"]
    }
}

SP_GET_ALLOWED_EDIT_OPTIONS_SCHEMA = {
    "name": "sp_get_allowed_edit_options",
    "description": "Get allowed edit options",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

# Doctor Finder tool schemas
DOCTOR_FINDER_LIST_SPECIALTIES_SCHEMA = {
    "name": "doctor_finder_list_specialties",
    "description": "Return all specialties (single source for UI selection)",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

DOCTOR_FINDER_LIST_DISTRICTS_SCHEMA = {
    "name": "doctor_finder_list_districts",
    "description": "Return all districts (single source for UI selection)",
    "parameters": {
        "type": "object",
        "properties": {}
    }
}

DOCTOR_FINDER_SEARCH_PROVIDERS_SCHEMA = {
    "name": "doctor_finder_search_providers",
    "description": "Search providers by free-text, returning matches for disambiguation",
    "parameters": {
        "type": "object",
        "properties": {
            "providerFreeText": {
                "type": "string",
                "description": "free text to search for providers"
            },
            "limit": {
                "type": "integer",
                "description": "maximum number of results to return",
                "default": 10
            }
        },
        "required": ["providerFreeText"]
    }
}

DOCTOR_FINDER_GET_DOCTOR_DETAILS_SCHEMA = {
    "name": "doctor_finder_get_doctor_details",
    "description": "Fetch a single doctor record by ID",
    "parameters": {
        "type": "object",
        "properties": {
            "doctorId": {
                "type": "string",
                "description": "the doctor id to lookup"
            }
        },
        "required": ["doctorId"]
    }
}

DOCTOR_FINDER_SEARCH_SCHEMA = {
    "name": "doctor_finder_search",
    "description": "Search panel doctors by filters",
    "parameters": {
        "type": "object",
        "properties": {
            "specialtyId": {
                "type": "string",
                "description": "specialty ID (mandatory)"
            },
            "districtId": {
                "type": "string",
                "description": "district ID (optional)"
            },
            "gender": {
                "type": "string",
                "description": "doctor gender (optional)"
            },
            "doctorName": {
                "type": "string",
                "description": "doctor name for free-text search (optional)"
            },
            "providerName": {
                "type": "string",
                "description": "provider name for free-text search (optional)"
            },
            "providerId": {
                "type": "string",
                "description": "provider ID (optional)"
            },
            "limit": {
                "type": "integer",
                "description": "maximum number of results per page",
                "default": 10
            },
            "pageToken": {
                "type": "string",
                "description": "pagination token for next page"
            }
        },
        "required": ["specialtyId"]
    }
}


def create_mcp_server():
    """Create and configure the MCP server."""
    app = Server("adk-mcp-http-server")

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[mcp_types.ContentBlock]:
        """Handle tool calls from the MCP client."""
        if name == "get_user_policy_and_products":
            client_id = arguments.get("client_id", [])
            if not client_id:
                error_text = json.dumps({"error": "The client_id parameter is required."})
                return [
                    mcp_types.TextContent(
                        type="text", text=error_text
                    )
                ]
            result = get_user_policy_and_products(client_id)
            return [mcp_types.TextContent(type="text", text=result)]
        
        if name == "get_user_client_id_list":
            user_id = arguments.get("user_id", "")
            if not user_id:
                error_text = json.dumps({"error": "The user_id parameter is required."})
                return [
                    mcp_types.TextContent(
                        type="text", text=error_text
                    )
                ]
            result = get_user_client_id_list(user_id)
            return [mcp_types.TextContent(type="text", text=result)]
        
        # Booking tools
        if name == "sp_get_customer":
            customer_id = arguments.get("customer_id", "")
            result = sp_get_customer(customer_id)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_list_policies":
            customer_id = arguments.get("customer_id", "")
            result = sp_list_policies(customer_id)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_list_life_assured":
            customer_id = arguments.get("customer_id", "")
            result = sp_list_life_assured(customer_id)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_check_eligibility":
            customer_id = arguments.get("customer_id", "")
            policy_id = arguments.get("policy_id", "")
            result = sp_check_eligibility(customer_id, policy_id)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_list_locations":
            result = sp_list_locations()
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_list_specialties":
            result = sp_list_specialties()
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_get_slot_windows":
            result = sp_get_slot_windows()
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_get_todays_date":
            result = sp_get_todays_date()
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_validate_appointment_draft":
            draft = arguments.get("draft", {})
            result = sp_validate_appointment_draft(draft)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_build_confirmation_summary":
            draft = arguments.get("draft", {})
            result = sp_build_confirmation_summary(draft)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_save_confirmed_appointment":
            confirmed_draft = arguments.get("confirmed_draft", {})
            idempotency_key = arguments.get("idempotency_key")
            result = sp_save_confirmed_appointment(confirmed_draft, idempotency_key)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_get_appointment_by_id":
            appointment_id = arguments.get("appointment_id", "")
            result = sp_get_appointment_by_id(appointment_id)
            return [mcp_types.TextContent(type="text", text=result)]

        if name == "sp_get_allowed_edit_options":
            result = sp_get_allowed_edit_options()
            return [mcp_types.TextContent(type="text", text=result)]

        # Doctor Finder tools
        if name == "doctor_finder_list_specialties":
            result = doctor_finder_list_specialties()
            return [mcp_types.TextContent(type="text", text=result)]
        
        if name == "doctor_finder_list_districts":
            result = doctor_finder_list_districts()
            return [mcp_types.TextContent(type="text", text=result)]
        
        if name == "doctor_finder_search_providers":
            provider_free_text = arguments.get("providerFreeText", "")
            limit = arguments.get("limit", 10)
            result = doctor_finder_search_providers(provider_free_text, limit)
            return [mcp_types.TextContent(type="text", text=result)]
        
        if name == "doctor_finder_get_doctor_details":
            doctor_id = arguments.get("doctorId", "")
            result = doctor_finder_get_doctor_details(doctor_id)
            return [mcp_types.TextContent(type="text", text=result)]
        
        if name == "doctor_finder_search":
            result = doctor_finder_search(
                specialty_id=arguments.get("specialtyId", ""),
                district_id=arguments.get("districtId"),
                gender=arguments.get("gender"),
                doctor_name=arguments.get("doctorName"),
                provider_name=arguments.get("providerName"),
                provider_id=arguments.get("providerId"),
                limit=arguments.get("limit", DEFAULT_PAGE_SIZE),
                page_token=arguments.get("pageToken")
            )
            return [mcp_types.TextContent(type="text", text=result)]
        
        else:
            raise ValueError(f"Unknown tool: {name}")

    @app.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        """List available tools."""
        return [
            mcp_types.Tool(
                name=GET_USER_POLICY_AND_PRODUCTS_SCHEMA["name"],
                description=GET_USER_POLICY_AND_PRODUCTS_SCHEMA["description"],
                inputSchema=GET_USER_POLICY_AND_PRODUCTS_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=GET_USER_CLIENT_ID_SCHEMA["name"],
                description=GET_USER_CLIENT_ID_SCHEMA["description"],
                inputSchema=GET_USER_CLIENT_ID_SCHEMA["parameters"]
            ),
            # Booking tools
            mcp_types.Tool(
                name=SP_GET_CUSTOMER_SCHEMA["name"],
                description=SP_GET_CUSTOMER_SCHEMA["description"],
                inputSchema=SP_GET_CUSTOMER_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_LIST_POLICIES_SCHEMA["name"],
                description=SP_LIST_POLICIES_SCHEMA["description"],
                inputSchema=SP_LIST_POLICIES_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_LIST_LIFE_ASSURED_SCHEMA["name"],
                description=SP_LIST_LIFE_ASSURED_SCHEMA["description"],
                inputSchema=SP_LIST_LIFE_ASSURED_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_CHECK_ELIGIBILITY_SCHEMA["name"],
                description=SP_CHECK_ELIGIBILITY_SCHEMA["description"],
                inputSchema=SP_CHECK_ELIGIBILITY_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_LIST_LOCATIONS_SCHEMA["name"],
                description=SP_LIST_LOCATIONS_SCHEMA["description"],
                inputSchema=SP_LIST_LOCATIONS_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_LIST_SPECIALTIES_SCHEMA["name"],
                description=SP_LIST_SPECIALTIES_SCHEMA["description"],
                inputSchema=SP_LIST_SPECIALTIES_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_GET_SLOT_WINDOWS_SCHEMA["name"],
                description=SP_GET_SLOT_WINDOWS_SCHEMA["description"],
                inputSchema=SP_GET_SLOT_WINDOWS_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_GET_TODAYS_DATE_SCHEMA["name"],
                description=SP_GET_TODAYS_DATE_SCHEMA["description"],
                inputSchema=SP_GET_TODAYS_DATE_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_VALIDATE_APPOINTMENT_DRAFT_SCHEMA["name"],
                description=SP_VALIDATE_APPOINTMENT_DRAFT_SCHEMA["description"],
                inputSchema=SP_VALIDATE_APPOINTMENT_DRAFT_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_BUILD_CONFIRMATION_SUMMARY_SCHEMA["name"],
                description=SP_BUILD_CONFIRMATION_SUMMARY_SCHEMA["description"],
                inputSchema=SP_BUILD_CONFIRMATION_SUMMARY_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_SAVE_CONFIRMED_APPOINTMENT_SCHEMA["name"],
                description=SP_SAVE_CONFIRMED_APPOINTMENT_SCHEMA["description"],
                inputSchema=SP_SAVE_CONFIRMED_APPOINTMENT_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_GET_APPOINTMENT_BY_ID_SCHEMA["name"],
                description=SP_GET_APPOINTMENT_BY_ID_SCHEMA["description"],
                inputSchema=SP_GET_APPOINTMENT_BY_ID_SCHEMA["parameters"]
            ),
            mcp_types.Tool(
                name=SP_GET_ALLOWED_EDIT_OPTIONS_SCHEMA["name"],
                description=SP_GET_ALLOWED_EDIT_OPTIONS_SCHEMA["description"],
                inputSchema=SP_GET_ALLOWED_EDIT_OPTIONS_SCHEMA["parameters"]
            ),
        ]

    return app

def create_mcp_lifespan_and_handler():
    """Creates the MCP lifespan manager and request handler."""
    app = create_mcp_server()
    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        stateless=True,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage the lifecycle of the session manager."""
        async with session_manager.run():
            logger.info("MCP Streamable HTTP server started!")
            yield

    async def handle_request(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    return lifespan, handle_request


