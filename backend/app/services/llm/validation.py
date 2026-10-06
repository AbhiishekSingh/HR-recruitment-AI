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


# Mirrors prompts/resume_extraction.py's SECTOR_LIST -- kept as its own
# allow-list here (rather than importing the prompt module) so validation
# has no dependency on prompt-building code, matching the existing
# VALID_RECOMMENDATIONS pattern below. MUST stay in sync with that list and
# with the frontend's SECTOR_LIST in types/index.ts -- update all three
# together whenever a sector is added or renamed.
VALID_SECTORS = {
    "IT", "HR", "Sales", "Marketing", "Finance", "Operations",
    "Customer Support", "Legal", "Design", "Healthcare", "Education",
    "Engineering", "Manufacturing", "Banking & Insurance",
    "Retail & E-commerce", "Hospitality & Travel",
    "Construction & Real Estate", "Logistics & Supply Chain",
    "Media & Entertainment", "Government & Public Sector", "Agriculture",
    "Other",
}


def _as_sector(value) -> str | None:
    """Coerces to one of VALID_SECTORS, or None if the model returned
    nothing usable -- None (not "Other") when the field is entirely absent,
    so a candidate genuinely un-classified (e.g. an old profile predating
    this feature) is distinguishable from one the model explicitly filed
    under "Other"."""
    s = _as_clean_str(value)
    if not s:
        return None
    # Case-insensitive match against the allow-list, since a reasoning
    # model occasionally varies casing ("it" / "Sales " with padding)
    # even when told to match exactly.
    for candidate in VALID_SECTORS:
        if candidate.lower() == s.lower():
            return candidate
    return "Other"


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
        "sector": _as_sector(raw.get("sector")),
        "position_role": _as_clean_str(raw.get("position_role")) or None,
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


def _as_non_negative(value) -> float | None:
    f = _as_float(value)
    return f if f is not None and f >= 0 else None


def coerce_jd_form_extraction(raw: dict) -> dict:
    """Pre-fill values for the requisition form. Numbers the JD didn't
    state stay None (never 0) so the form can highlight them for HR."""
    if not isinstance(raw, dict):
        raw = {}
    title = raw.get("title")
    title = title.strip()[:300] if isinstance(title, str) and title.strip() else None

    budget_min = _as_non_negative(raw.get("budget_min_inr"))
    budget_max = _as_non_negative(raw.get("budget_max_inr"))
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        budget_min, budget_max = budget_max, budget_min

    exp_min = _as_non_negative(raw.get("experience_min_years"))
    exp_max = _as_non_negative(raw.get("experience_max_years"))
    if exp_min is not None and exp_min > 60:
        exp_min = None
    if exp_max is not None and exp_max > 60:
        exp_max = None
    if exp_min is not None and exp_max is not None and exp_min > exp_max:
        exp_min, exp_max = exp_max, exp_min

    notice = _as_non_negative(raw.get("max_notice_days"))
    notice_days = int(round(notice)) if notice is not None and notice <= 365 else None

    required = _as_str_list(raw.get("required_skills"))
    nice = [s for s in _as_str_list(raw.get("nice_to_have_skills")) if s not in required]

    groups = []
    for g in raw.get("skill_groups") or []:
        if not isinstance(g, dict):
            continue
        skills = _as_str_list(g.get("skills"))[:20]
        if not skills:
            continue
        gtype = g.get("type") if g.get("type") in ("must", "nice", "soft") else "must"
        name = g.get("name").strip()[:80] if isinstance(g.get("name"), str) and g.get("name").strip() else skills[0]
        groups.append({"name": name, "type": gtype, "skills": skills,
                       "synonyms": _as_str_list(g.get("synonyms"))[:20]})
        if len(groups) >= 15:
            break
    # Make sure every listed required/nice skill sits in some group.
    grouped = {s.lower() for g in groups for s in g["skills"]}
    for s in required:
        if s.lower() not in grouped:
            groups.append({"name": s, "type": "must", "skills": [s], "synonyms": []})
    for s in nice:
        if s.lower() not in grouped:
            groups.append({"name": s, "type": "nice", "skills": [s], "synonyms": []})

    return {
        "skill_groups": groups[:15],
        "related_titles": _as_str_list(raw.get("related_titles"))[:6],
        "title": title,
        "locations": _as_str_list(raw.get("locations")),
        "budget_min": budget_min,
        "budget_max": budget_max,
        "experience_min": exp_min,
        "experience_max": exp_max,
        "max_notice_days": notice_days,
        "required_skills": required,
        "nice_to_have_skills": nice,
        "responsibilities": _as_str_list(raw.get("responsibilities")),
        "qualifications": _as_str_list(raw.get("qualifications")),
        "hard_requirements": _as_str_list(raw.get("hard_requirements")),
    }
