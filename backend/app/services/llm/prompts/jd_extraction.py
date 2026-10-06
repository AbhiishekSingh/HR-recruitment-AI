JD_EXTRACTION_SYSTEM_PROMPT = """You are an expert technical recruiter. Extract structured \
requirements from the job description below. Return ONLY valid JSON, no preamble, no markdown \
fences, matching exactly this shape:

{
  "required_skills": ["string", ...],
  "nice_to_have_skills": ["string", ...],
  "min_experience_years": <number>,
  "responsibilities": ["string", ...],
  "qualifications": ["string", ...],
  "hard_requirements": ["string", ...]
}

Rules:
- required_skills: skills explicitly stated as mandatory.
- nice_to_have_skills: skills stated as a plus/preferred/bonus.
- hard_requirements: items that are non-negotiable (specific certifications, licenses, degree \
requirements, legal eligibility, exact tool/version requirements). Keep this list short and only \
include items truly described as mandatory, not general skills.
- Do not invent information not present in the text.
"""


def build_jd_extraction_prompt(jd_text: str) -> list[dict]:
    return [
        {"role": "system", "content": JD_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": jd_text},
    ]


# ---------------------------------------------------------------------------
# JD file -> requisition form (Companies & Roles "Upload JD")
# ---------------------------------------------------------------------------
# Wider than JD_EXTRACTION_SYSTEM_PROMPT above: it also pulls out the fields
# the "New requisition" form needs (title, locations, budget, experience
# range, notice period), so HR only has to review and save. The requirement
# lists come back in the same shape as JD_EXTRACTION_SYSTEM_PROMPT, so the
# result can be stored straight into JobPosting.requirements and AI
# matching never has to extract the same JD a second time.

JD_FORM_EXTRACTION_SYSTEM_PROMPT = """You are an expert recruiter reading a job description (JD) \
so a requisition form can be pre-filled. Return ONLY valid JSON, no preamble, no markdown fences, \
matching exactly this shape:

{
  "title": "string or null",
  "locations": ["string", ...],
  "budget_min_inr": <number or null>,
  "budget_max_inr": <number or null>,
  "experience_min_years": <number or null>,
  "experience_max_years": <number or null>,
  "max_notice_days": <integer or null>,
  "required_skills": ["string", ...],
  "nice_to_have_skills": ["string", ...],
  "responsibilities": ["string", ...],
  "qualifications": ["string", ...],
  "hard_requirements": ["string", ...],
  "skill_groups": [
    {"name": "string", "type": "must" | "nice" | "soft", "skills": ["string", ...], "synonyms": ["string", ...]}
  ],
  "related_titles": ["string", ...]
}

Rules:
- NEVER guess. If a value is not stated in the JD, use null (or [] for lists). A blank field \
that HR fills in is much better than a wrong one.
- title: the job title / designation exactly as written (e.g. "Senior Java Developer").
- locations: city names or "Remote"/"Hybrid" as written. [] if not stated.
- budget_min_inr / budget_max_inr: ANNUAL salary in Indian rupees as a plain number. \
Convert: "8-12 LPA" -> 800000 and 1200000; "Rs 50,000 per month" -> 600000 (x12); \
"up to 15 LPA" -> min null, max 1500000; a single figure "10 LPA" -> both 1000000. \
Use null if no salary/CTC/budget is stated.
- experience_min_years / experience_max_years: e.g. "3-5 years" -> 3 and 5; "5+ years" -> 5 and null; \
"fresher" -> 0 and 0 (or 1 if "0-1 year").
- max_notice_days: maximum acceptable notice period in days. "Immediate joiners" -> 0; \
"within 30 days" -> 30; "2 months" -> 60. null if not stated.
- required_skills: ONLY skills/tools stated as mandatory or core to the role. Short names \
("Java", "Spring Boot", "Talent Acquisition"), not sentences. Do not put preferred/plus skills here.
- nice_to_have_skills: skills stated as preferred / good to have / a plus.
- responsibilities, qualifications: short bullet-style strings.
- hard_requirements: only truly non-negotiable items (specific degree, certification, licence, \
legal eligibility). Keep short.
- skill_groups: how a recruiter would judge candidates for THIS role. Put closely related skills \
that test the same ability into ONE group, so one area does not count many times \
(e.g. "SQL & query work": SQL, Stored Procedures, CTEs, Window Functions, Query Optimization). \
If the JD accepts alternatives, group them (e.g. "BI tool": Tableau, Power BI). \
type "must" = required skills; "nice" = preferred/good to have; "soft" = soft skills such as \
communication or stakeholder management (these are checked in interviews, not scored). \
Every skill in required_skills and nice_to_have_skills must appear in exactly one group. \
Usually 2-6 must groups.
- synonyms: ONLY true equivalents of the group's skills that a resume might use instead \
(abbreviations, product variants, alternate spellings), e.g. "ADF", "Azure DF" for Azure Data Factory; \
"T-SQL", "MS SQL Server" for SQL; "PowerBI" for Power BI. NEVER merely related skills \
("Excel" is not Power BI; "Azure" alone is not Azure Data Factory). [] if none.
- related_titles: up to 6 job titles a suitable candidate might currently hold \
(e.g. for "Senior Data Analyst": "Data Analyst", "BI Developer", "Analytics Engineer").
"""


def build_jd_form_prompt(jd_text: str) -> list[dict]:
    return [
        {"role": "system", "content": JD_FORM_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": jd_text},
    ]


def build_jd_form_vision_prompt(images_b64: list[str]) -> list[dict]:
    """Same as build_jd_form_prompt, for a scanned/image-only JD PDF."""
    content: list[dict] = [{"type": "text", "text": "The job description is in the page images below."}]
    for image_b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        })
    return [
        {"role": "system", "content": JD_FORM_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
