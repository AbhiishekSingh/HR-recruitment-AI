# Fixed sector vocabulary -- kept in one place (also mirrored in
# validation.py's VALID_SECTORS allow-list and the frontend's SECTOR_LIST in
# types/index.ts -- all three MUST be updated together when this list
# changes) since the sector-cards landing page filters candidates by exact
# match on this value, so the model must pick from this closed list rather
# than free-text.
#
# Healthcare/Education/Engineering were added after a real miss: a
# "Consultant Gynecological Minimal Access Surgeon" resume had no valid
# bucket to go into (the original list was built around a generic
# office/corporate recruiting agency and had no clinical, teaching, or core
# engineering category at all) and was forced into "Other" -- not because
# the model misread the resume, but because the category genuinely didn't
# exist. "Other" should only ever catch a resume that truly doesn't fit any
# real sector, not an entire profession the list forgot to include. If a
# new gap like this shows up again, the fix is the same: add the missing
# sector here (+ the two mirrors above), not tune the prompt wording.
SECTOR_LIST = [
    "IT", "HR", "Sales", "Marketing", "Finance", "Operations",
    "Customer Support", "Legal", "Design", "Healthcare", "Education",
    "Engineering", "Manufacturing", "Banking & Insurance",
    "Retail & E-commerce", "Hospitality & Travel",
    "Construction & Real Estate", "Logistics & Supply Chain",
    "Media & Entertainment", "Government & Public Sector", "Agriculture",
    "Other",
]

# Suggested (not exhaustive) position titles per sector -- a starting
# vocabulary the model should prefer, but it may return a different, close
# real-world title if the resume's actual title doesn't fit any of these
# cleanly (e.g. "DevOps Engineer" under IT, "Talent Acquisition Specialist"
# under HR, "Consultant Gynecological Surgeon" under Healthcare). This keeps
# position_role useful for grouping/search without forcing every real-world
# title into a handful of buckets -- unlike `sector`, `position_role` is
# semi-open vocabulary (see coerce_resume_extraction), so an unusual real
# title is never coerced away the way an unrecognized sector would be.
SUGGESTED_POSITIONS = {
    "IT": ["Full Stack Developer", "Backend Developer", "Frontend Developer", "QA Engineer", "DevOps Engineer", "Data Engineer", "Data Scientist"],
    "HR": ["HR Recruiter", "HR Payroll", "HR Generalist", "Talent Acquisition Specialist", "HR Business Partner"],
    "Sales": ["Sales Executive", "Business Development Executive", "Account Manager", "Sales Manager"],
    "Marketing": ["Digital Marketing Executive", "SEO Specialist", "Content Marketer", "Marketing Manager"],
    "Finance": ["Accountant", "Financial Analyst", "Auditor"],
    "Operations": ["Operations Executive", "Operations Manager", "Supply Chain Analyst"],
    "Customer Support": ["Customer Support Executive", "Technical Support Engineer"],
    "Legal": ["Legal Associate", "Compliance Officer"],
    "Design": ["UI/UX Designer", "Graphic Designer"],
    # Any clinical/medical role -- general or specialist physicians and
    "Healthcare": [
        "Consultant Physician", "Consultant Surgeon", "General Practitioner",
        "Specialist Doctor", "Dentist", "Staff Nurse", "Nursing Officer",
        "Pharmacist", "Physiotherapist", "Radiologist", "Medical Officer",
        "Lab Technician", "Hospital Administrator",
    ],
    "Education": ["Teacher", "Lecturer", "Professor", "Academic Coordinator", "Principal", "Curriculum Developer", "Trainer"],
    # Core/non-software engineering disciplines -- a software/computer
    # engineer still belongs under IT (see the classification rule below);
    # this sector is for mechanical, civil, electrical, and similar roles.
    "Engineering": ["Mechanical Engineer", "Civil Engineer", "Electrical Engineer", "Quality Engineer", "Site Engineer"],
    # Shop-floor/plant roles -- distinct from Engineering (design/technical
    # discipline) and from Logistics & Supply Chain (movement/storage of
    # goods, not making them).
    "Manufacturing": ["Production Supervisor", "Plant Manager", "Machine Operator", "Assembly Line Worker", "Maintenance Technician", "Production Engineer", "Manufacturing Engineer"],
    "Banking & Insurance": ["Relationship Manager", "Loan Officer", "Bank Teller", "Underwriter", "Insurance Agent", "Credit Analyst", "Branch Manager"],
    # Store-based and online commerce -- distinct from "Sales" (generic
    # B2B/corporate sales roles across any industry).
    "Retail & E-commerce": ["Store Manager", "Retail Sales Associate", "Merchandiser", "Category Manager", "E-commerce Manager", "Visual Merchandiser"],
    "Hospitality & Travel": ["Hotel Manager", "Front Desk Executive", "Chef", "Travel Consultant", "Cabin Crew", "Housekeeping Supervisor", "Event Manager"],
    "Construction & Real Estate": ["Site Supervisor", "Real Estate Agent", "Property Manager", "Quantity Surveyor", "Architect", "Civil Site Engineer"],
    # Movement/storage/procurement of goods -- distinct from "Operations"
    # (generic business/office operations not specific to a supply chain).
    "Logistics & Supply Chain": ["Warehouse Manager", "Supply Chain Manager", "Logistics Coordinator", "Fleet Manager", "Procurement Officer", "Dispatch Executive"],
    # Journalism/broadcast/film/content production as the core business --
    # distinct from "Marketing" (brand/digital marketing for a product or
    # company) and from "Design" (UI/UX and graphic design).
    "Media & Entertainment": ["Content Producer", "Video Editor", "Journalist", "Copywriter", "Social Media Manager", "Anchor", "Film/TV Production Executive"],
    "Government & Public Sector": ["Government Officer", "Policy Analyst", "Public Administrator", "Civil Servant"],
    "Agriculture": ["Agronomist", "Farm Manager", "Agricultural Engineer", "Veterinarian"],
}

RESUME_EXTRACTION_SYSTEM_PROMPT = f"""You are an expert resume parser. Extract structured \
candidate information from the resume text below. Return ONLY valid JSON, no preamble, no \
markdown fences, matching exactly this shape:

{{
  "candidate_name": "string",
  "candidate_email": "string",
  "candidate_phone": "string",
  "current_company": "string",
  "skills": ["string", ...],
  "work_history": [
    {{"role": "string", "company": "string", "duration": "string", "achievements": ["string", ...]}}
  ],
  "education": [
    {{"degree": "string", "institution": "string", "year": "string"}}
  ],
  "certifications": ["string", ...],
  "total_experience_years": <number>,
  "sector": "string",
  "position_role": "string"
}}

Rules:
- candidate_name/candidate_email/candidate_phone: pulled from the resume's header/contact
  section, exactly as written. Leave as an empty string if genuinely not present in the text
  -- never invent a name, email, or phone number.
- current_company: the employer from the most recent work_history entry, if any.
- Extract skills mentioned explicitly anywhere in the resume (summary, skills section, and \
implied by project/work bullets).
- total_experience_years should be a reasonable estimate from the work history dates.
- Do not invent information not present in the text. Leave arrays empty if nothing is found.
- degree (in education): expand abbreviations to their full standard form -- write "Bachelor
  of Science" not "B.Sc" or "BSc", "Bachelor of Technology" not "B.Tech", "Master of Business
  Administration" not "MBA", and so on for any other degree abbreviation. This keeps the same
  degree spelled the same way across different resumes, which is what candidate search filters
  on. (The backend also normalizes common spelling variants at search time as a second layer,
  so this isn't the only thing making search work -- but consistent extraction means less for
  that layer to have to cover.)

Sector/position classification (sector and position_role fields):
- Base the classification on the candidate's MOST RECENT job only (the first/most recent entry
  of work_history, i.e. their current or latest role) -- not the whole resume and not their
  earliest job. An experienced HR professional whose latest role is "HR Payroll" is classified
  as HR / HR Payroll, even if an earlier job in their history was something else entirely.
- If the candidate has NO work history at all (a fresher/student with no prior jobs), classify
  instead from their stated career objective, most relevant coursework/major, projects, or
  skills section -- whichever best indicates the field they are entering.
- sector MUST be exactly one of this fixed list (case-sensitive, pick the closest fit; use
  "Other" only if truly nothing fits -- a medical, teaching, or core-engineering resume is
  NEVER "Other", since Healthcare/Education/Engineering exist specifically to cover those):
  {SECTOR_LIST}
- "Healthcare" covers ANY clinical/medical role at any seniority or specialization -- a
  general physician, a nurse, and a highly specialized consultant surgeon (e.g. "Consultant
  Gynecological Minimal Access Surgeon") are all "Healthcare". Do not be thrown by an unusually
  long or specialized real-world title -- classify by what kind of work it fundamentally is
  (practicing medicine), not by whether the exact title appears in the suggested-positions list.
- "IT" is for software/computer/data roles specifically. "Engineering" is for other, non-software
  design/technical engineering disciplines (mechanical, civil, electrical, quality, site
  engineering). A "Software Engineer" or "DevOps Engineer" is IT, not Engineering, despite the
  word "Engineer" in the title -- classify by the actual discipline the work is in, not by
  job-title keyword matching.
- "Manufacturing" is shop-floor/plant production roles (machine operators, production
  supervisors, plant managers) -- distinct from "Engineering" (the technical/design discipline)
  and from "Logistics & Supply Chain" (moving/storing/procuring goods, not making them).
- "Sales" is generic B2B/corporate sales across any industry; "Retail & E-commerce" is
  store-based or online commerce roles specifically (store manager, retail associate,
  merchandiser, e-commerce manager).
- "Operations" is generic business/office operations; "Logistics & Supply Chain" is specifically
  warehousing, shipping, fleet, dispatch, and procurement roles.
- "Marketing" is brand/digital/product marketing; "Design" is UI/UX and graphic design; "Media &
  Entertainment" is journalism, broadcasting, and film/TV/content production as the core
  business -- a candidate can look like they overlap two of these, so classify by what the
  employer's core business/the role's core output actually is.
- position_role should be the candidate's actual, real-world job title for that most recent
  role (or intended role, for a fresher) wherever possible. Prefer a title from this
  suggested-but-not-exhaustive list for the chosen sector when it's a good fit, but if the
  resume's real title is close-but-different (e.g. "DevOps Engineer" for IT, "Consultant
  Gynecological Minimal Access Surgeon" for Healthcare), return that real title instead of
  forcing it into the list: {SUGGESTED_POSITIONS}
- Never leave sector empty -- always pick the closest-fitting value from the fixed list.
"""


def build_resume_extraction_prompt(resume_text: str) -> list[dict]:
    return [
        {"role": "system", "content": RESUME_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": resume_text},
    ]


def build_resume_transcription_prompt(images_b64: list[str]) -> list[dict]:
    """A second, separate vision call for scanned/image-only PDFs: unlike
    build_resume_vision_prompt (which asks for the structured JSON schema),
    this asks the model to transcribe the resume's visible text verbatim,
    line by line, with no JSON wrapper and no summarizing/paraphrasing. The
    output becomes CandidateProfile.raw_text for a scanned resume (see
    tasks_ingestion.py) -- without it, a scanned resume only has a short
    synthesized skills/experience summary on file, which the full-text
    resume search (`GET /candidates/search-resumes`) can't usefully search
    line-by-line the way it can a text-layer resume."""
    content: list[dict] = [
        {
            "type": "text",
            "text": "These images are the pages of a resume, in order. Transcribe ALL visible "
            "text exactly as it appears, preserving line breaks (one resume line per output "
            "line, in reading order, top to bottom within each page and page order after "
            "that). Do not summarize, reorder, or omit anything -- headings, bullet points, "
            "dates, contact details, all of it. Do not add any commentary, preamble, or "
            "markdown formatting -- output only the transcribed text itself.",
        }
    ]
    for image_b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        })
    return [
        {"role": "system", "content": "You are a precise document transcription assistant."},
        {"role": "user", "content": content},
    ]


def build_resume_vision_prompt(images_b64: list[str]) -> list[dict]:
    """Same extraction schema/rules as the text prompt, but the resume is
    supplied as page images instead of extracted text -- for scanned/
    image-only PDFs where no text layer exists to extract in the first
    place. Each image is sent as a data-URI `image_url` content part,
    which is how the Chat Completions API accepts vision input."""
    content: list[dict] = [
        {
            "type": "text",
            "text": "These images are the pages of a resume, in order. Read them and "
            "extract the same structured JSON described in your instructions.",
        }
    ]
    for image_b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        })
    return [
        {"role": "system", "content": RESUME_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
