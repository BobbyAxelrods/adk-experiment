"""doctor_finder.py

Doctor Finder tools for PHKL Thin Slice Part 2 (Mock).

Usage (recommended):
    from mcp.server.fastmcp import FastMCP
    from tools.doctor_finder import register_doctor_finder_tools

    mcp = FastMCP("PHKL MCP", json_response=True)
    register_doctor_finder_tools(mcp)

This module does not start the server. It only registers tools.
It relies on JSON fixtures under DATA_DIR (default: ./mcp_mock_data).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "mcp_mock_data"
DATA_DIR = Path(os.getenv("PHKL_MCP_DATA_DIR", str(DEFAULT_DATA_DIR)))

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


def _load_json(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing mock data file: {path}. Set PHKL_MCP_DATA_DIR or place fixtures under ./mcp_mock_data"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_text(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _safe_int(s: Optional[str], default: int = 0) -> int:
    try:
        return int(s) if s is not None else default
    except Exception:
        return default


def _paginate(items: List[Dict[str, Any]], page_token: Optional[str], limit: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    offset = _safe_int(page_token, 0)
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    page = items[offset : offset + limit]
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


def _register_doctor_finder_tools(mcp, *, datasets: Optional[Dict[str, Any]] = None) -> None:
    """Register Doctor Finder tools on an existing FastMCP instance.

    Parameters
    ----------
    mcp:
        FastMCP server instance.
    datasets:
        Optional override for in-memory datasets. Keys:
        districts, specialties, providers, doctors.
        If omitted, data is loaded from JSON fixtures.
    """

    data = datasets or {}
    districts = data.get("districts") or _load_json("districts.json")
    specialties = data.get("specialties") or _load_json("specialties.json")
    providers = data.get("providers") or _load_json("providers.json")
    doctors = data.get("doctors") or _load_json("doctors.json")

    @mcp.tool()
    def doctorFinder_listSpecialties() -> Dict[str, Any]:
        """Return all specialties (single source for UI selection)."""
        return {"specialties": specialties}

    @mcp.tool()
    def doctorFinder_listDistricts() -> Dict[str, Any]:
        """Return all districts (single source for UI selection)."""
        return {"districts": districts}

    @mcp.tool()
    def doctorFinder_searchProviders(providerFreeText: str, limit: int = 10) -> Dict[str, Any]:
        """Search providers by free-text, returning matches for disambiguation."""
        q = _normalize_text(providerFreeText)
        matches = [p for p in providers if _match_fuzzy(q, p.get("name", ""))]
        matches.sort(key=lambda x: (not bool(x.get("preferred")), x.get("name", "")))
        return {
            "query": providerFreeText,
            "providers": matches[: max(1, min(limit, MAX_PAGE_SIZE))],
        }

    @mcp.tool()
    def doctorFinder_getDoctorDetails(doctorId: str) -> Dict[str, Any]:
        """Fetch a single doctor record by ID."""
        for d in doctors:
            if d.get("doctor_id") == doctorId:
                provider = next((p for p in providers if p.get("provider_id") == d.get("provider_id")), None)
                return {"doctor": d, "provider": provider}
        return {"doctor": None, "provider": None, "error": "DOCTOR_NOT_FOUND"}

    @mcp.tool()
    def doctorFinder_search(
        specialtyId: str,
        districtId: Optional[str] = None,
        gender: Optional[str] = None,
        doctorName: Optional[str] = None,
        providerName: Optional[str] = None,
        providerId: Optional[str] = None,
        limit: int = DEFAULT_PAGE_SIZE,
        pageToken: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search panel doctors by filters.

        Rules supported:
        - Specialty is mandatory.
        - District and gender are optional (None means "No preference").
        - Doctor name/provider name can be used for free-text narrowing.
        - Preferred providers first.
        - Pagination via pageToken/limit.
        """
        if not specialtyId:
            return {"error": "SPECIALTY_REQUIRED", "doctors": [], "count": 0, "nextPageToken": None}

        dn = _normalize_text(doctorName)
        pn = _normalize_text(providerName)

        results: List[Dict[str, Any]] = []
        for d in doctors:
            if d.get("specialty_id") != specialtyId:
                continue
            if districtId and d.get("district_id") != districtId:
                continue
            if gender and d.get("gender") != gender:
                continue
            if providerId and d.get("provider_id") != providerId:
                continue
            if dn and not _match_fuzzy(dn, d.get("name", "")):
                continue
            if pn and not _match_fuzzy(pn, d.get("provider_name", "")):
                continue
            results.append(d)

        results.sort(key=lambda x: (not bool(x.get("preferred")), x.get("name", "")))
        page, next_token = _paginate(results, pageToken, limit)

        return {
            "filters": {
                "specialtyId": specialtyId,
                "districtId": districtId,
                "gender": gender,
                "doctorName": doctorName,
                "providerName": providerName,
                "providerId": providerId,
            },
            "count": len(results),
            "doctors": page,
            "nextPageToken": next_token,
            "noResults": len(results) == 0,
        }
