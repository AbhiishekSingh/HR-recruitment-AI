"""Free "smart score" (0-100) for every candidate in a job's pipeline -- no
AI call. Used to rank the pipeline, and to pick which candidates are worth
an (optional, paid) AI score.

    Must-have skill groups   50%  each group counts once; synonyms; skills + full resume text
    Meaning match            20%  JD vs resume embeddings (already paid for at upload)
    Experience fit           15%
    Role / title relevance   10%
    Nice-to-have             5%
    Soft skills               0%  checked in the screening call instead

A part with no data (no embedding yet, no titles found, no nice-to-have
groups) is left out and the remaining weights are scaled up, so a missing
input never silently counts as zero.
"""
from __future__ import annotations

import re

from app.services.search.skill_matcher import CandidateText, expand, find, seniority_words, tokens

WEIGHTS = {"must": 50, "meaning": 20, "experience": 15, "title": 10, "nice": 5}

# text-embedding-3-large cosine similarity between a JD summary and a resume
# summary: ~0.20 = unrelated, ~0.55+ = very close. Mapped linearly to 0-1.
# Tunable if real data shows a different spread.
SIM_LOW = 0.20
SIM_HIGH = 0.55


def experience_fit(years: float | None, exp_min: float, exp_max: float) -> float | None:
    if years is None:
        return None
    exp_min = exp_min or 0
    exp_max = exp_max or 0
    if exp_min == 0 and exp_max == 0:
        return 1.0  # no requirement set
    if exp_max and exp_max < exp_min:
        exp_min, exp_max = exp_max, exp_min
    if exp_min <= years <= (exp_max or years):
        return 1.0
    if years < exp_min:
        return max(0.0, 1 - (exp_min - years) * 0.25)
    return max(0.4, 1 - (years - exp_max) * 0.08)


def _core_tokens(title: str) -> list[str]:
    stop = seniority_words()
    return [t for t in tokens(title) if t not in stop]


def title_relevance(job_title: str, related_titles: list[str], candidate_titles: list[str]) -> tuple[float | None, str]:
    cand = [t for t in candidate_titles if t and t.strip()]
    if not cand:
        return None, ""
    cand_core = [(t, _core_tokens(t)) for t in cand]
    # A combined title ("Data Analyst & Database Engineer") is several roles:
    # matching any one of them counts as a full role match.
    wanted_titles = [job_title, *related_titles]
    for part in re.split(r"\s*(?:&|/|,|\||\band\b)\s*", job_title or "", flags=re.IGNORECASE):
        if part.strip() and part.strip() != job_title:
            wanted_titles.append(part.strip())
    # exact role match (ignoring seniority words) against job title or a related title
    for wanted in wanted_titles:
        w = _core_tokens(wanted)
        if not w:
            continue
        for original, ct in cand_core:
            if " " + " ".join(w) + " " in " " + " ".join(ct) + " ":
                return 1.0, original
    # partial: share of the job title's key words found in a candidate title
    job_core = set(_core_tokens(job_title))
    if not job_core:
        return None, ""
    best, best_title = 0.0, ""
    for original, ct in cand_core:
        overlap = len(job_core & set(ct)) / len(job_core)
        if overlap > best:
            best, best_title = overlap, original
    return round(best * 0.8, 3), best_title  # partial overlap never counts as a full match


def _group_terms(group: dict) -> list[str]:
    terms: list[str] = []
    for skill in group["skills"]:
        terms.extend(expand(skill))
    terms.extend(group.get("synonyms") or [])
    return terms


def smart_score(
    *,
    job,
    config: dict,
    skills: list[str] | None,
    full_text: str | None,
    experience_years: float | None,
    candidate_titles: list[str],
    similarity: float | None,
) -> dict:
    cand = CandidateText.build(skills, full_text)

    evidence: list[dict] = []
    must_total = must_hit = nice_total = nice_hit = 0
    for group in config["skill_groups"]:
        if group["type"] == "soft":
            evidence.append({"group": group["name"], "type": "soft", "matched": None, "found": None, "where": None})
            continue
        hit = find(cand, _group_terms(group))
        evidence.append({
            "group": group["name"], "type": group["type"], "matched": bool(hit),
            "found": hit[0] if hit else None, "where": hit[1] if hit else None,
        })
        if group["type"] == "must":
            must_total += 1
            must_hit += 1 if hit else 0
        else:
            nice_total += 1
            nice_hit += 1 if hit else 0

    meaning = None
    if similarity is not None:
        meaning = max(0.0, min(1.0, (similarity - SIM_LOW) / (SIM_HIGH - SIM_LOW)))
    exp = experience_fit(experience_years, job.experience_min, job.experience_max)
    title, title_found = title_relevance(job.title, config.get("related_titles", []), candidate_titles)

    values = {
        "must": (must_hit / must_total) if must_total else None,
        "meaning": meaning,
        "experience": exp,
        "title": title,
        "nice": (nice_hit / nice_total) if nice_total else None,
    }
    used = {k: v for k, v in values.items() if v is not None}
    weight_sum = sum(WEIGHTS[k] for k in used)
    score = round(sum(WEIGHTS[k] * v for k, v in used.items()) / weight_sum * 100) if weight_sum else 0

    parts = [
        {"key": "must", "label": "Must-have skills", "weight": WEIGHTS["must"],
         "value": None if values["must"] is None else round(values["must"] * 100),
         "detail": f"{must_hit}/{must_total} groups" if must_total else "no must-have groups"},
        {"key": "meaning", "label": "Meaning match", "weight": WEIGHTS["meaning"],
         "value": None if meaning is None else round(meaning * 100),
         "detail": "" if similarity is not None else "not available yet"},
        {"key": "experience", "label": "Experience", "weight": WEIGHTS["experience"],
         "value": None if exp is None else round(exp * 100),
         "detail": f"{experience_years:g} yrs vs {job.experience_min:g}–{job.experience_max:g}" if experience_years is not None else "unknown"},
        {"key": "title", "label": "Role / title", "weight": WEIGHTS["title"],
         "value": None if title is None else round(title * 100),
         "detail": title_found or ("no job titles found" if title is None else "")},
        {"key": "nice", "label": "Nice-to-have", "weight": WEIGHTS["nice"],
         "value": None if values["nice"] is None else round(values["nice"] * 100),
         "detail": f"{nice_hit}/{nice_total}" if nice_total else "none listed"},
    ]

    flags: list[dict] = []
    missing = [e["group"] for e in evidence if e["type"] == "must" and not e["matched"]]
    if missing:
        flags.append({"level": "info", "text": "Missing must-have: " + ", ".join(missing)})
    if exp is not None and exp < 0.5 and experience_years is not None:
        flags.append({"level": "warn", "text": f"{experience_years:g} yrs experience vs required {job.experience_min:g}–{job.experience_max:g}"})

    return {
        "score": max(0, min(100, score)),
        "source": "smart",
        "parts": parts,
        "evidence": evidence,
        "matched_skills": [e["group"] for e in evidence if e["matched"]],
        "missing_skills": missing,
        "flags": flags,
    }
