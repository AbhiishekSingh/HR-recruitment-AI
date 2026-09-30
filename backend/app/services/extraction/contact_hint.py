"""
Cheap, non-LLM extraction of an email/phone "hint" from a resume's raw text
-- used only for the pre-upload duplicate check (see
`POST /candidates/check-duplicate` in candidates.py), NOT for the real
structured extraction (that's still GPT-5's job, in tasks_ingestion.py).

Why regex instead of GPT-5 here: the duplicate check has to happen
synchronously, in the moment between the recruiter picking a file and it
actually being uploaded, so a recruiter can be asked "this candidate might
already exist -- replace / keep both / cancel?" before anything is written.
Running a real GPT-5 extraction call per file at that point would add
several seconds of latency (and cost) per file, for every file, even the
large majority that aren't duplicates. Email and phone number are both
regular enough in format that a plain regex over the extracted text finds
them reliably without any of that -- this never touches the LLM.
"""

import re

# Standard email pattern -- deliberately simple (no attempt at the full RFC
# grammar) since a resume's contact section is written by a human for a
# human to read, not adversarially malformed.
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Matches a run of 10-15 digits allowing the common separators/prefixes
# (spaces, hyphens, parens, a leading +country code) a resume's contact
# section uses -- deliberately permissive on formatting since normalization
# (normalize_phone below) is what actually makes two different-looking
# numbers comparable, not this regex.
_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s()]{8,}\d)")


def extract_email_hint(text: str) -> str | None:
    """First email-shaped string found in `text`, or None. Resumes
    occasionally list more than one (a personal + a "current work" email);
    the first one is almost always the primary contact one, which is good
    enough for a duplicate hint (the real extraction in tasks_ingestion.py
    is what actually populates Candidate.email)."""
    match = _EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def normalize_phone(raw: str) -> str | None:
    """Strips everything but digits and keeps the last 10 -- India-centric
    (10-digit mobile numbers), but tolerant of a leading country code ("+91",
    "0") or formatting (spaces/hyphens/parens) by just discarding whatever
    comes before the last 10 digits. Returns None if fewer than 10 digits
    remain (too short to be a real phone number, not worth comparing)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10:
        return None
    return digits[-10:]


def extract_phone_hint(text: str) -> str | None:
    """First phone-shaped, normalizable number found in `text`, or None."""
    for match in _PHONE_RE.finditer(text):
        normalized = normalize_phone(match.group(0))
        if normalized:
            return normalized
    return None
