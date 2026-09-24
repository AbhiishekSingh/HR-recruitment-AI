RESUME_EXTRACTION_SYSTEM_PROMPT = """You are an expert resume parser. Extract structured \
candidate information from the resume text below. Return ONLY valid JSON, no preamble, no \
markdown fences, matching exactly this shape:

{
  "candidate_name": "string",
  "candidate_email": "string",
  "candidate_phone": "string",
  "current_company": "string",
  "skills": ["string", ...],
  "work_history": [
    {"role": "string", "company": "string", "duration": "string", "achievements": ["string", ...]}
  ],
  "education": [
    {"degree": "string", "institution": "string", "year": "string"}
  ],
  "certifications": ["string", ...],
  "total_experience_years": <number>
}

Rules:
- candidate_name/candidate_email/candidate_phone: pulled from the resume's header/contact
  section, exactly as written. Leave as an empty string if genuinely not present in the text
  -- never invent a name, email, or phone number.
- current_company: the employer from the most recent work_history entry, if any.
- Extract skills mentioned explicitly anywhere in the resume (summary, skills section, and \
implied by project/work bullets).
- total_experience_years should be a reasonable estimate from the work history dates.
- Do not invent information not present in the text. Leave arrays empty if nothing is found.
"""


def build_resume_extraction_prompt(resume_text: str) -> list[dict]:
    return [
        {"role": "system", "content": RESUME_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": resume_text},
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
