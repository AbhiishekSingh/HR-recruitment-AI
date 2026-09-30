"""
Query-time normalization for the Candidates directory's search/filter
endpoints (skills, qualification, and the plain search box).

The problem: extraction is an LLM call, so the exact string it writes for a
degree or a skill varies resume to resume -- "B.Sc", "BSc", "B.Sc.", and
"Bachelor of Science" are all the same qualification, but a plain ILIKE
substring match treats them as four unrelated strings; same for "React",
"ReactJS", "React.js". Re-running extraction to force one canonical spelling
across every already-ingested resume isn't practical (and the prompt change
in resume_extraction.py only helps *new* uploads going forward, see its
"Normalize degree names" rule).

The fix applied here has two parts, both query-side so it works retroactively
on data that's already in the database:

1. Punctuation/case-insensitive matching: "B.Sc" and "BSc" become the same
   string once periods/spaces are stripped and it's lowercased, so a plain
   substring match against the *normalized* text catches spelling variants
   that share the same letters.
2. Synonym expansion: "BSc" and "Bachelor of Science" don't share letters at
   all, so no amount of punctuation-stripping helps -- this needs an actual
   alias table. When a search term matches a known alias group, every alias
   in that group is OR-matched, not just the term as typed.

This is deliberately a fixed, hand-maintained list covering common
degrees/tech skills, not a general synonym engine -- good enough for a
recruiting tool's search box without needing an embeddings-based fuzzy match
for this particular problem.
"""

import re

# Each group's key is just a label for readability; what matters is the list
# of variant spellings, which are the terms treated as interchangeable.
QUALIFICATION_GROUPS: list[list[str]] = [
    ["bachelor of science", "bsc", "b sc", "b.sc", "b.sc."],
    ["bachelor of technology", "btech", "b tech", "b.tech", "b.tech.", "bachelor of engineering", "be", "b.e", "b.e."],
    ["bachelor of commerce", "bcom", "b com", "b.com", "b.com."],
    ["bachelor of arts", "ba", "b.a", "b.a.", "bachelor's in arts"],
    ["bachelor of business administration", "bba", "b.b.a"],
    ["bachelor of computer applications", "bca", "b.c.a"],
    ["master of science", "msc", "m sc", "m.sc", "m.sc."],
    ["master of technology", "mtech", "m tech", "m.tech", "m.tech.", "master of engineering", "me", "m.e", "m.e."],
    ["master of business administration", "mba", "m.b.a"],
    ["master of computer applications", "mca", "m.c.a"],
    ["master of commerce", "mcom", "m com", "m.com", "m.com."],
    ["master of arts", "ma", "m.a", "m.a."],
    ["doctor of philosophy", "phd", "ph d", "ph.d", "ph.d."],
    ["diploma", "diploma"],
    ["higher secondary", "12th", "hsc", "intermediate", "senior secondary"],
    ["secondary school", "10th", "ssc", "matriculation"],
]

SKILL_GROUPS: list[list[str]] = [
    ["react", "reactjs", "react.js", "react js"],
    ["node", "nodejs", "node.js", "node js"],
    ["javascript", "js"],
    ["typescript", "ts"],
    ["python"],
    ["postgresql", "postgres", "psql"],
    ["mysql", "my sql"],
    ["mongodb", "mongo"],
    ["amazon web services", "aws"],
    ["google cloud platform", "gcp"],
    ["microsoft azure", "azure"],
    ["kubernetes", "k8s"],
    ["docker"],
    ["machine learning", "ml"],
    ["artificial intelligence", "ai"],
    ["natural language processing", "nlp"],
    ["html5", "html"],
    ["css3", "css"],
    ["next.js", "nextjs", "next js"],
    ["vue.js", "vuejs", "vue js", "vue"],
    ["angular.js", "angularjs", "angular"],
    [".net", "dotnet", "dot net"],
    ["c#", "csharp", "c sharp"],
    ["c++", "cpp"],
    ["ci/cd", "cicd", "ci cd"],
    ["power bi", "powerbi"],
    ["search engine optimization", "seo"],
    ["search engine marketing", "sem"],
    ["human resources", "hr"],
    ["customer relationship management", "crm"],
    ["enterprise resource planning", "erp"],
]


def _normalize(s: str) -> str:
    """Lowercase and strip everything but letters/digits, so "B.Sc.", "b sc"
    and "BSc" all collapse to the same "bsc" -- this is what makes
    normalized-text matching catch punctuation/spacing variants without
    needing them listed as separate aliases."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _build_lookup(groups: list[list[str]]) -> dict[str, list[str]]:
    """Maps every normalized alias to its full group (including itself), so
    looking up any one spelling returns every spelling in that group."""
    lookup: dict[str, list[str]] = {}
    for group in groups:
        for alias in group:
            lookup[_normalize(alias)] = group
    return lookup


_QUALIFICATION_LOOKUP = _build_lookup(QUALIFICATION_GROUPS)
_SKILL_LOOKUP = _build_lookup(SKILL_GROUPS)


def expand_term(term: str, lookup: dict[str, list[str]]) -> list[str]:
    """Given what a person typed, returns every equivalent spelling worth
    OR-matching against. Falls back to just the term itself (still
    punctuation/case-normalized downstream) when it's not a known alias --
    this only helps recognized degrees/skills, it doesn't invent synonyms
    for arbitrary free text."""
    normalized = _normalize(term)
    group = lookup.get(normalized)
    if group:
        return group
    return [term]


def expand_qualification(term: str) -> list[str]:
    return expand_term(term, _QUALIFICATION_LOOKUP)


def expand_skill(term: str) -> list[str]:
    return expand_term(term, _SKILL_LOOKUP)


def normalize_for_sql(term: str) -> str:
    """The normalized form to search FOR inside already-normalized column
    text (see candidates.py's `_normalized_contains` helper, which applies
    the matching regexp_replace to the column side)."""
    return _normalize(term)
