"""
Scoring engine for the ATS pipeline.

Score used for a candidate in a job ("ai" in compute_final_score):
  * an up-to-date on-demand AI score (MatchResult row whose
    requirements_hash matches the job's current settings + the resume), or
  * otherwise the free smart score (services/scoring/smart_score.py: skill
    groups with synonyms, meaning match, experience, title, nice-to-have).
An AI score that no longer matches (job edited / resume replaced) is shown
as out of date until HR re-scores it.

Final score = 60% that score + 40% the recruiter's screening assessment.
ai_match_score() below is the old word-for-word estimate, kept only for
reference -- nothing calls it any more.
"""

from app.services.scoring.job_config import effective_config, profile_version, scoring_hash
from app.services.scoring.smart_score import smart_score

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


def _from_match_result(match_result) -> dict:
    """Adapts a MatchResult ORM row (the real GPT-5 pipeline's output) into
    the same shape ai_match_score() returns, so nothing downstream has to
    know which source produced it."""
    return {
        "score": match_result.score,
        "matched_skills": match_result.matched_skills or [],
        "missing_skills": match_result.missing_skills or [],
        "strengths": match_result.strengths or [],
        "gaps": match_result.gaps or [],
        "recommendation": match_result.recommendation,
        "model_version": match_result.model_version,
        "scored_at": match_result.scored_at,
        "source": "ai_pipeline",
    }


def sanity_check_ai_score(ai: dict) -> list[dict]:
    """Cheap, non-LLM check that the GPT-5 score roughly agrees with the
    matched/missing skill lists it returned alongside it. Never blocks or
    overrides anything — it only surfaces a flag for the recruiter to glance
    at, since the human always makes the final call (see final_status /
    compute_final_score's hard_reject logic)."""
    if ai.get("source") != "ai_pipeline":
        return []

    matched = len(ai.get("matched_skills") or [])
    missing = len(ai.get("missing_skills") or [])
    total = matched + missing
    if total == 0:
        return []

    coverage = matched / total
    score = ai.get("score", 0)
    # A high score with mostly-missing skills, or a low score with
    # mostly-matched skills, means the LLM's number and its own stated
    # reasoning disagree — worth a human glance, not an auto-correction.
    if score >= 70 and coverage < 0.4:
        return [{"level": "warn", "text": f"AI score ({score}) is high but only {matched}/{total} required skills matched — worth a second look."}]
    if score <= 40 and coverage > 0.75:
        return [{"level": "warn", "text": f"AI score ({score}) is low despite {matched}/{total} required skills matched — worth a second look."}]
    return []


def ai_match_score(job_skills: list[str], candidate_skills: list[str],
                    candidate_experience_years: float, exp_min: float, exp_max: float) -> dict:
    """FALLBACK ONLY — pure keyword overlap + experience-band fit, used only
    when no MatchResult exists yet for this (job, candidate) pair (AI
    pipeline hasn't run, or this candidate wasn't in the pre-filtered
    top-K). Interface (score/matched/missing) matches _from_match_result()
    so callers don't need to branch on which one they got."""
    job_skills_norm = [s.strip().lower() for s in job_skills]
    cand_skills_norm = [s.strip().lower() for s in candidate_skills]

    matched = [s for s in job_skills if s.strip().lower() in cand_skills_norm]
    missing = [s for s in job_skills if s.strip().lower() not in cand_skills_norm]
    skill_coverage = (len(matched) / len(job_skills)) if job_skills else 0

    candidate_experience_years = candidate_experience_years or 0

    if exp_min == 0 and exp_max == 0:
        # JobPosting.experience_min/max default to 0/0 when a recruiter
        # hasn't set an experience range yet. Without this guard, the "over"
        # branch below treats that as "the job wants 0 years" and penalizes
        # every experienced candidate down to a floor of 0.5 — the opposite
        # of what an unset range should mean. Unset = no experience
        # requirement, so it's a full fit regardless of years.
        exp_fit = 1.0
    elif exp_min <= candidate_experience_years <= exp_max:
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
        "source": "estimate",
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


def candidate_titles(candidate, candidate_profile) -> list[str]:
    """Most recent job titles we know for the candidate (for title relevance)."""
    titles: list[str] = []
    for t in (getattr(candidate_profile, "position_role", None), getattr(candidate, "position_role", None)):
        if t:
            titles.append(t)
    history = getattr(candidate_profile, "work_history", None) or []
    if isinstance(history, list):
        for w in history[:3]:
            if isinstance(w, dict):
                t = w.get("role") or w.get("title") or w.get("designation")
                if isinstance(t, str) and t.strip():
                    titles.append(t.strip())
    return titles


def compute_final_score(job, candidate, a, match_result=None, candidate_profile=None,
                        config: dict | None = None, similarity: float | None = None) -> dict:
    """job = JobPosting, candidate = Candidate, a = Assessment, match_result =
    this pair's MatchResult (an on-demand AI score) if one exists,
    candidate_profile = the AI-extracted resume data, config = the job's
    effective scoring settings, similarity = JD-vs-resume embedding cosine.

    The score used ("ai") is the AI score when it is UP TO DATE (same job
    settings + same resume as when it was scored), otherwise the free smart
    score. An older AI score is reported as ai_stale so HR can re-score.

    AI involvement stops at `ai` below. Nothing here lets the AI set
    final_status or bucket on its own; that stays a human decision."""
    config = config or effective_config(job)
    if candidate_profile is not None:
        skills_source = candidate_profile.skills or []
        text_source = candidate_profile.raw_text or ""
        years = candidate_profile.total_experience_years
        if years is None:
            years = candidate.experience_years
    else:
        skills_source = candidate.resume_skills or []
        text_source = candidate.resume_summary or ""
        years = candidate.experience_years
    smart = smart_score(
        job=job, config=config, skills=skills_source, full_text=text_source,
        experience_years=years, candidate_titles=candidate_titles(candidate, candidate_profile),
        similarity=similarity,
    )

    ai_fresh = (
        match_result is not None and candidate_profile is not None
        and match_result.requirements_hash == scoring_hash(job, config, profile_version(candidate_profile))
    )
    ai_stale = match_result is not None and not ai_fresh
    if ai_fresh:
        ai = _from_match_result(match_result)
    else:
        ai = {
            "score": smart["score"],
            "matched_skills": smart["matched_skills"],
            "missing_skills": smart["missing_skills"],
            "source": "processing" if candidate.status in ("queued", "extracting", "embedding") else "smart",
        }

    ai_flags = sanity_check_ai_score(ai) + [f for f in smart["flags"] if f["level"] == "warn"]
    if ai_stale:
        ai_flags.append({"level": "info", "text": f"AI score {match_result.score} is out of date (job settings or resume changed) — smart score shown. Re-score to update."})
    if ai.get("source") != "ai_pipeline":
        if candidate.status in ("queued", "extracting", "embedding"):
            # The resume upload itself hasn't finished processing yet -- a
            # 0-skills estimate here means "no data yet", not "no match".
            # Without this, a recruiter has no way to tell those apart from
            # the pipeline view alone.
            ai_flags.append({"level": "info", "text": f"Resume is still processing ({candidate.status}) — skill/experience match will update once extraction finishes."})
        elif candidate.status == "needs_review":
            ai_flags.append({"level": "warn", "text": "Resume text extraction failed — this candidate needs manual review before an AI estimate is meaningful."})
        elif candidate.status == "failed":
            ai_flags.append({"level": "warn", "text": "Resume processing failed after retries — this candidate needs manual review."})

    extra = {"smart": smart, "ai_stale": ai_stale, "ai_previous_score": match_result.score if ai_stale else None}

    if not a.screened:
        return {
            **extra,
            "ai": ai, "assessment": None,
            "flags": ai_flags + [{"level": "warn", "text": "Awaiting recruiter screening — no assessment on file yet."}],
            "hard_reject": False, "adjustments": [], "final": None, "bucket": "pending",
        }

    assessment = assessment_score(a)
    filt = apply_hard_filters(job, a)
    flags, hard_reject = ai_flags + filt["flags"], filt["hard_reject"]

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

    return {**extra, "ai": ai, "assessment": assessment, "flags": flags, "hard_reject": hard_reject,
            "adjustments": adjustments, "final": final, "bucket": bucket}


BUCKET_LABELS = {
    "strong": "Strong Match", "good": "Good Match", "weak": "Weak Match",
    "notrec": "Not Recommended", "rejected": "Rejected", "pending": "Pending Screening",
}
