"""
PLACEHOLDER scoring engine.

This is a direct, deliberate port of the prototype's scoring.js logic — same
math, same weights, same hard-filter rules — so the ATS foundation is fully
real and working end-to-end right now, without waiting on the real AI work.

Everything under `ai_match_score()` below is a temporary stand-in for the
real pipeline that already exists elsewhere in this backend (GPT-5 structured
extraction + embeddings + hybrid search + GPT-5 scoring — see
services/llm/, services/embeddings/, services/search/hybrid_search.py).

When that pipeline is wired into this ATS flow, only `ai_match_score()` needs
to be replaced with a real lookup into `match_results` — nothing else in this
file, or in the assessment/job endpoints that call it, needs to change,
because the interface (a 0-100 score + matched/missing skills) stays the same.
"""

ENUM_MAPS = {
    "strong_partial_low": {"Strong": 100, "Partial": 60, "Low": 20},
    "good_avg_poor": {"Good": 100, "Average": 60, "Poor": 20},
    "high_mod_low": {"High": 100, "Moderate": 60, "Low": 20},
    "stability": {"Stable": 100, "Moderate": 60, "Frequent Changes": 20},
    "yes_no": {"Yes": 100, "No": 0},
}

ASSESSMENT_WEIGHTS = {
    "skills_match": 0.25,
    "experience_match": 0.20,
    "communication": 0.15,
    "interest_level": 0.15,
    "job_stability": 0.10,
    "cv_relevance": 0.10,
    "industry_alignment": 0.05,
}

FINAL_WEIGHTS = {"ai": 0.6, "assessment": 0.4}


def _enum_score(map_name: str, value: str) -> int:
    return ENUM_MAPS[map_name].get(value, 0)


def ai_match_score(job_skills: list[str], candidate_skills: list[str],
                    candidate_experience_years: float, exp_min: float, exp_max: float) -> dict:
    """PLACEHOLDER — pure keyword overlap + experience-band fit.
    Replace with a real match_results lookup once the GPT-5 pipeline is wired
    into this flow. Interface (score/matched/missing) is deliberately stable."""
    job_skills_norm = [s.strip().lower() for s in job_skills]
    cand_skills_norm = [s.strip().lower() for s in candidate_skills]

    matched = [s for s in job_skills if s.strip().lower() in cand_skills_norm]
    missing = [s for s in job_skills if s.strip().lower() not in cand_skills_norm]
    skill_coverage = (len(matched) / len(job_skills)) if job_skills else 0

    if exp_min <= candidate_experience_years <= exp_max:
        exp_fit = 1.0
    elif candidate_experience_years < exp_min:
        gap = exp_min - candidate_experience_years
        exp_fit = max(0.0, 1 - gap * 0.25)
    else:
        over = candidate_experience_years - exp_max
        exp_fit = max(0.5, 1 - over * 0.08)

    score = round((skill_coverage * 0.7 + exp_fit * 0.3) * 100)
    return {
        "score": max(0, min(100, score)),
        "matched_skills": matched,
        "missing_skills": missing,
        "skill_coverage": round(skill_coverage * 100),
        "experience_fit": round(exp_fit * 100),
    }


def assessment_score(a) -> dict:
    """`a` is an Assessment ORM instance or any object with the matching attrs."""
    parts = {
        "skills_match": _enum_score("strong_partial_low", a.skills_match),
        "experience_match": _enum_score("strong_partial_low", a.experience_match),
        "communication": _enum_score("good_avg_poor", a.communication),
        "interest_level": _enum_score("high_mod_low", a.interest_level),
        "job_stability": _enum_score("stability", a.job_stability),
        "cv_relevance": _enum_score("yes_no", a.cv_relevance),
        "industry_alignment": _enum_score("yes_no", a.industry_alignment),
    }
    total = sum(parts[k] * ASSESSMENT_WEIGHTS[k] for k in ASSESSMENT_WEIGHTS)
    return {"score": round(total), "parts": parts}


def apply_hard_filters(job, a) -> dict:
    flags = []
    hard_reject = False

    if a.expected_ctc is not None and job.budget_max and a.expected_ctc > job.budget_max:
        flags.append({"level": "reject", "text": f"Expected CTC exceeds budget max"})

    location_ok = (not job.locations) or a.preferred_location in job.locations or "Remote" in job.locations
    if not location_ok:
        flags.append({"level": "warn", "text": f'Preferred location "{a.preferred_location}" not in JD locations'})

    if a.notice_period_days is not None and a.notice_period_days > job.max_notice_days:
        flags.append({"level": "warn", "text": f"Notice period {a.notice_period_days}d exceeds JD max {job.max_notice_days}d"})

    if a.final_status == "Reject":
        hard_reject = True
        flags.append({"level": "reject", "text": "Recruiter marked Reject — excluded from shortlist"})

    if a.red_flags and a.red_flags.strip():
        flags.append({"level": "warn", "text": f"Red flag noted: {a.red_flags}"})

    return {"flags": flags, "hard_reject": hard_reject}


def compute_final_score(job, candidate, a) -> dict:
    """job = JobPosting ORM row, candidate = Candidate ORM row, a = Assessment ORM row."""
    ai = ai_match_score(
        job.required_skills, candidate.resume_skills,
        candidate.experience_years, job.experience_min, job.experience_max,
    )

    if not a.screened:
        return {
            "ai": ai, "assessment": None,
            "flags": [{"level": "warn", "text": "Awaiting recruiter screening — no assessment on file yet."}],
            "hard_reject": False, "adjustments": [], "final": None, "bucket": "pending",
        }

    assessment = assessment_score(a)
    filt = apply_hard_filters(job, a)
    flags, hard_reject = filt["flags"], filt["hard_reject"]

    final = FINAL_WEIGHTS["ai"] * ai["score"] + FINAL_WEIGHTS["assessment"] * assessment["score"]
    adjustments = []

    if a.red_flags and a.red_flags.strip():
        final -= 15
        adjustments.append({"text": "Red flag penalty", "value": -15})
    if a.salary_alignment == "No":
        final -= 10
        adjustments.append({"text": "Salary misalignment penalty", "value": -10})
    if a.notice_fit == "No":
        final -= 5
        adjustments.append({"text": "Notice period penalty", "value": -5})
    if a.final_status == "Share to Client":
        final += 5
        adjustments.append({"text": "Recruiter conviction bonus", "value": 5})
    if a.final_status == "Hold":
        final = min(final, 60)
        adjustments.append({"text": "Capped at 60 — recruiter marked Hold", "value": None})

    final = max(0, min(100, round(final)))

    if hard_reject:
        bucket = "rejected"
    elif final >= 80:
        bucket = "strong"
    elif final >= 60:
        bucket = "good"
    elif final >= 40:
        bucket = "weak"
    else:
        bucket = "notrec"

    return {"ai": ai, "assessment": assessment, "flags": flags, "hard_reject": hard_reject,
            "adjustments": adjustments, "final": final, "bucket": bucket}


BUCKET_LABELS = {
    "strong": "Strong Match", "good": "Good Match", "weak": "Weak Match",
    "notrec": "Not Recommended", "rejected": "Rejected", "pending": "Pending Screening",
}
