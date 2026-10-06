"""A job's scoring settings: skill groups + related job titles.

Stored on JobPosting.scoring_config as
    {"skill_groups": [{"name", "type": "must"|"nice"|"soft", "skills": [...], "synonyms": [...]}],
     "related_titles": [...]}
Filled from the JD (AI suggestion) and edited by HR in Edit job. Jobs that
don't have it yet (older jobs, or typed in by hand without groups) get a
free automatic default built from their required skills -- see
default_skill_groups().
"""
from __future__ import annotations

import hashlib
import json

from app.services.search.skill_matcher import canonical, families, is_soft_skill, norm

GROUP_TYPES = ("must", "nice", "soft")
MAX_GROUPS = 15
MAX_ITEMS = 20


def _clean_list(values, limit: int = MAX_ITEMS) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        if not isinstance(v, str):
            continue
        v = v.strip()[:100]
        key = norm(v)
        if v and key and key not in seen:
            seen.add(key)
            out.append(v)
        if len(out) >= limit:
            break
    return out


def sanitize_groups(raw_groups) -> list[dict]:
    groups: list[dict] = []
    for g in raw_groups or []:
        if not isinstance(g, dict):
            continue
        skills = _clean_list(g.get("skills"))
        if not skills:
            continue
        gtype = g.get("type") if g.get("type") in GROUP_TYPES else "must"
        name = (g.get("name") or "").strip()[:80] or skills[0]
        groups.append({
            "name": name,
            "type": gtype,
            "skills": skills,
            "synonyms": _clean_list(g.get("synonyms")),
        })
        if len(groups) >= MAX_GROUPS:
            break
    return groups


def sanitize_config(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "skill_groups": sanitize_groups(raw.get("skill_groups")),
        "related_titles": _clean_list(raw.get("related_titles"), limit=10),
    }


def default_skill_groups(required: list[str], nice: list[str] | None = None) -> list[dict]:
    """Free fallback grouping for jobs without HR/AI groups:
    - soft skills (communication, stakeholder management...) -> not scored
    - required skills from the same family (SQL, Stored Procedures, CTEs...)
      -> ONE must-have group, so one area can't dominate the score
    - every other required skill -> its own must-have group
    - nice-to-have skills -> one nice-to-have group each
    """
    family_of: dict[str, str] = {}
    for fam, members in families().items():
        for m in members:
            family_of[norm(m)] = fam

    groups: list[dict] = []
    by_family: dict[str, dict] = {}
    soft: list[str] = []
    for skill in _clean_list(required, limit=40):
        if is_soft_skill(skill):
            soft.append(skill)
            continue
        fam = family_of.get(norm(canonical(skill))) or family_of.get(norm(skill))
        if fam:
            if fam not in by_family:
                by_family[fam] = {"name": fam, "type": "must", "skills": [], "synonyms": []}
                groups.append(by_family[fam])
            by_family[fam]["skills"].append(skill)
        else:
            groups.append({"name": skill, "type": "must", "skills": [skill], "synonyms": []})
    for skill in _clean_list(nice, limit=20):
        if is_soft_skill(skill):
            soft.append(skill)
        else:
            groups.append({"name": skill, "type": "nice", "skills": [skill], "synonyms": []})
    if soft:
        groups.append({"name": "Soft skills", "type": "soft", "skills": soft, "synonyms": []})
    return groups[:MAX_GROUPS]


def effective_config(job) -> dict:
    """The config actually used for scoring this job (saved, or default)."""
    saved = sanitize_config(getattr(job, "scoring_config", None))
    if saved["skill_groups"]:
        return {**saved, "is_default": False}
    nice = []
    if isinstance(job.requirements, dict):
        nice = job.requirements.get("nice_to_have_skills") or []
    return {
        "skill_groups": default_skill_groups(job.required_skills or [], nice),
        "related_titles": saved["related_titles"],
        "is_default": True,
    }


def must_skills(groups: list[dict]) -> list[str]:
    return _clean_list([s for g in groups if g["type"] == "must" for s in g["skills"]], limit=60)


def nice_skills(groups: list[dict]) -> list[str]:
    return _clean_list([s for g in groups if g["type"] == "nice" for s in g["skills"]], limit=60)


def ai_requirements(job, config: dict) -> dict:
    """What the AI scorer is given about the job."""
    req = job.requirements if isinstance(job.requirements, dict) else {}
    return {
        "title": job.title,
        "experience_years": {"min": job.experience_min, "max": job.experience_max},
        "skill_groups": [
            {k: g[k] for k in ("name", "type", "skills", "synonyms")} for g in config["skill_groups"]
        ],
        "related_titles": config.get("related_titles", []),
        "responsibilities": req.get("responsibilities", []),
        "qualifications": req.get("qualifications", []),
        "hard_requirements": req.get("hard_requirements", []),
    }


def scoring_hash(job, config: dict, extraction_model_version: str | None) -> str:
    """Changes whenever anything the AI score depends on changes -- used to
    mark an existing AI score "out of date" after Edit job / new resume."""
    payload = json.dumps(
        {"requirements": ai_requirements(job, config), "extraction": extraction_model_version or ""},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def profile_version(profile) -> str:
    """Identifies the resume data an AI score was based on: extraction model
    + a fingerprint of the resume text, so replacing a candidate's resume
    marks their old AI score "out of date"."""
    if profile is None:
        return ""
    text = getattr(profile, "raw_text", "") or ""
    digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]
    return f"{getattr(profile, 'extraction_model_version', '') or ''}:{digest}"


def job_embedding_text(job, config: dict) -> str:
    """Text embedded for the job's "meaning match" -- same shape as the
    candidate side (_build_embedding_summary in tasks_ingestion.py)."""
    req = job.requirements if isinstance(job.requirements, dict) else {}
    skills = ", ".join(s for g in config["skill_groups"] if g["type"] != "soft" for s in g["skills"])
    resp = "; ".join(req.get("responsibilities", [])[:15])
    titles = ", ".join([job.title, *config.get("related_titles", [])])
    return f"Skills: {skills}\nExperience: {titles}: {resp}"
