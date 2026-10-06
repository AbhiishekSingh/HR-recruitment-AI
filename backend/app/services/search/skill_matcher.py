"""Skill / synonym matching shared by the Candidates search box and the free
candidate scoring.

Global synonyms live in app/data/skill_synonyms.json (one file, edited by a
developer, applied on restart). Per-job synonyms (AI-suggested from the JD,
editable by HR) are passed in by the caller.

Matching works on TOKENS, not raw substrings, so "Java" never matches
"JavaScript" and "SQL" never matches inside "PostgreSQL":

  * text is lower-cased; c#, c++, .net are protected; everything that isn't
    a letter/digit becomes a space -> "Power-BI" -> ["power", "bi"]
  * a term matches if its tokens appear consecutively ("power bi"), or if
    its letters joined together appear as one token ("powerbi")
  * very short terms (2 letters or fewer: "ai", "ml", "sp", "r") are only
    matched against the candidate's extracted skill list, never against
    free resume text, where they cause false matches ("will be", "SP road").
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SYNONYMS_FILE = Path(__file__).resolve().parents[2] / "data" / "skill_synonyms.json"

SHORT_TERM_MAX_LEN = 2

_PROTECT = [
    (re.compile(r"c\s*#"), " csharp "),
    (re.compile(r"c\s*\+\s*\+"), " cpp "),
    (re.compile(r"(?<![a-z0-9])\.net\b"), " dotnet "),
]


def _protect(text: str) -> str:
    out = text.lower()
    for pattern, repl in _PROTECT:
        out = pattern.sub(repl, out)
    return out


def tokens(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", _protect(text or "")).split()


def norm(term: str) -> str:
    """Canonical comparison key: letters/digits only ("Power-BI" -> "powerbi")."""
    return "".join(tokens(term))


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        with open(SYNONYMS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _groups(section: str) -> list[list[str]]:
    groups = []
    for canonical, aliases in (_load().get(section) or {}).items():
        groups.append([canonical, *[a for a in (aliases or []) if isinstance(a, str)]])
    return groups


@lru_cache(maxsize=1)
def _skill_lookup() -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for group in _groups("skills"):
        for term in group:
            lookup.setdefault(norm(term), group)
    return lookup


def skill_groups_for_search() -> list[list[str]]:
    """For term_normalization (search box)."""
    return _groups("skills")


def qualification_groups_for_search() -> list[list[str]]:
    return _groups("qualifications")


def families() -> dict[str, list[str]]:
    return dict(_load().get("families") or {})


@lru_cache(maxsize=1)
def soft_skill_keys() -> frozenset[str]:
    return frozenset(norm(s) for s in (_load().get("soft_skills") or []))


@lru_cache(maxsize=1)
def seniority_words() -> frozenset[str]:
    return frozenset(w.lower() for w in (_load().get("seniority_words") or []))


def is_soft_skill(term: str) -> bool:
    return norm(term) in soft_skill_keys()


def canonical(term: str) -> str:
    group = _skill_lookup().get(norm(term))
    return group[0] if group else term.strip()


def expand(term: str, extra: list[str] | None = None) -> list[str]:
    """`term` plus every global synonym of it, plus `extra` (per-job synonyms)."""
    out: list[str] = []
    seen: set[str] = set()
    for t in [term, *(_skill_lookup().get(norm(term)) or []), *(extra or [])]:
        key = norm(t)
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


@dataclass
class CandidateText:
    """Pre-tokenised candidate data, built once per candidate per request."""
    skill_keys: set[str] = field(default_factory=set)          # norm() of each extracted skill
    skill_token_seqs: list[list[str]] = field(default_factory=list)
    text_padded: str = " "                                      # " tok tok tok " of the full resume
    text_tokens: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, skills: list[str] | None, full_text: str | None) -> "CandidateText":
        skills = [s for s in (skills or []) if isinstance(s, str)]
        toks = tokens(full_text or "")
        return cls(
            skill_keys={norm(s) for s in skills if norm(s)},
            skill_token_seqs=[tokens(s) for s in skills],
            text_padded=" " + " ".join(toks) + " ",
            text_tokens=set(toks),
        )


def _in_seq(needle: list[str], hay_padded: str) -> bool:
    return bool(needle) and (" " + " ".join(needle) + " ") in hay_padded


def find(cand: CandidateText, terms: list[str]) -> tuple[str, str] | None:
    """First of `terms` found for this candidate, as (term, where) with
    where = "skills" or "resume", else None."""
    for term in terms:
        t_tokens = tokens(term)
        key = "".join(t_tokens)
        if not key:
            continue
        # 1) extracted skill list: exact item, or term inside a skill item
        if key in cand.skill_keys:
            return term, "skills"
        if len(key) > SHORT_TERM_MAX_LEN:
            for seq in cand.skill_token_seqs:
                if _in_seq(t_tokens, " " + " ".join(seq) + " ") or key in seq:
                    return term, "skills"
    for term in terms:
        t_tokens = tokens(term)
        key = "".join(t_tokens)
        if len(key) <= SHORT_TERM_MAX_LEN:
            continue
        # 2) full resume text (work history, projects, summary...)
        if _in_seq(t_tokens, cand.text_padded) or (len(t_tokens) > 1 and key in cand.text_tokens):
            return term, "resume"
    return None


def reload_synonyms() -> None:
    """Clears cached synonym data (tests / admin reload)."""
    for fn in (_load, _skill_lookup, soft_skill_keys, seniority_words):
        fn.cache_clear()
