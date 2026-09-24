"""
Coerces/validates the JSON each LLM call returns before it's trusted by the
rest of the app. `response_format={"type": "json_object"}` only guarantees
syntactically valid JSON -- it does not guarantee the model filled in every
key, used the right type for each value, or stayed within a declared range.
In practice this means: a missing key, a "score" returned as a numeric
string, an experience value with a stray "~" or "+" in it, a hallucinated
extra field, or a recommendation string that doesn't match one of the three
allowed values. Any of those, uncaught, either crashes deep inside a Celery
task on a DB type error or silently corrupts a match/profile row.

Every function here is defensive by construction: on anything unexpected it
falls back to a safe default (empty list, None, "Review") rather than
raising, because a slightly-off AI response should degrade to "flagged for
human review", never take down the ingestion/matching pipeline for every
candidate behind it in the queue.
"""


def _as_str_list(value) -> list[str]:
    """Coerces to a list of non-empty strings. Handles: not a list at all
    (single string, None, a dict) -> best-effort wrap or []; a list with
    non-string items (numbers, nested dicts/lists) -> stringified or dropped."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                out.append(item.strip())
        elif isinstance(item, (int, float)):
            out.append(str(item))
        # dicts/lists/None inside the list are dropped, not stringified --
        # a hallucinated {"skill": "Python"} instead of "Python" isn't
        # recoverable as a clean skill string.
    return out


def _as_float(value) -> float | None:
    """Coerces to a float, tolerating common LLM formatting quirks like
    "5+", "~3.5", "4 years". Returns None (not 0) when nothing usable is
    present, since 0 years and "unknown" are meaningfully different
    downstream (see ai_match_score's null-guard)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == ".")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _as_int_in_range(value, *, default: int, lo: int, hi: int) -> int:
    f = _as_float(value)
    if f is None:
        return default
    return max(lo, min(hi, round(f)))


def coerce_jd_extraction(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "required_skills": _as_str_list(raw.get("required_skills")),
        "nice_to_have_skills": _as_str_list(raw.get("nice_to_have_skills")),
        "min_experience_years": _as_float(raw.get("min_experience_years")),
        "responsibilities": _as_str_list(raw.get("responsibilities")),
        "qualifications": _as_str_list(raw.get("qualifications")),
        "hard_requirements": _as_str_list(raw.get("hard_requirements")),
    }


def _as_work_history(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append({
            "role": str(item.get("role") or ""),
            "company": str(item.get("company") or ""),
            "duration": str(item.get("duration") or ""),
            "achievements": _as_str_list(item.get("achievements")),
        })
    return out


def _as_education(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        out.append({
            "degree": str(item.get("degree") or ""),
            "institution": str(item.get("institution") or ""),
            "year": str(item.get("year") or ""),
        })
    return out


def _as_clean_str(value) -> str:
    """Coerces to a plain string, trimmed. Never invents a value -- returns
    "" for None/missing/non-string junk (a hallucinated dict/list in a
    name/email/phone field), matching the extraction prompt's "leave empty
    if not present" rule."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def coerce_resume_extraction(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "candidate_name": _as_clean_str(raw.get("candidate_name")),
        "candidate_email": _as_clean_str(raw.get("candidate_email")),
        "candidate_phone": _as_clean_str(raw.get("candidate_phone")),
        "current_company": _as_clean_str(raw.get("current_company")),
        "skills": _as_str_list(raw.get("skills")),
        "work_history": _as_work_history(raw.get("work_history")),
        "education": _as_education(raw.get("education")),
        "certifications": _as_str_list(raw.get("certifications")),
        "total_experience_years": _as_float(raw.get("total_experience_years")),
    }


VALID_RECOMMENDATIONS = {"Shortlist", "Review", "Pass"}


def coerce_score_result(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}

    recommendation = raw.get("recommendation")
    if recommendation not in VALID_RECOMMENDATIONS:
        # Defaults to "Review", never "Shortlist" -- an unparseable
        # recommendation should route to a human, not silently promote a
        # candidate. Matches the project's hard rule that AI never
        # auto-decides Reject/Shortlist; this just keeps that rule intact
        # even when the model's own output is malformed.
        recommendation = "Review"

    return {
        "score": _as_int_in_range(raw.get("score"), default=0, lo=0, hi=100),
        "matched_skills": _as_str_list(raw.get("matched_skills")),
        "missing_skills": _as_str_list(raw.get("missing_skills")),
        "strengths": _as_str_list(raw.get("strengths")),
        "gaps": _as_str_list(raw.get("gaps")),
        "recommendation": recommendation,
    }
