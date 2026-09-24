from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

# How much slack to give below the JD's stated minimum experience before a
# candidate is pre-filtered out. Not zero: exp_min is often a soft target in
# practice (a recruiter's "3-5 years" JD shouldn't hard-exclude someone at
# 2.5), and the real experience-fit scoring/penalty already lives in
# ai_match_score()/placeholder_engine.py. This filter only needs to remove
# candidates who are obviously out of range, not make the final call.
EXPERIENCE_FLOOR_BUFFER_YEARS = 2.0


async def hybrid_search(
    db: AsyncSession,
    query_embedding: list[float],
    query_keywords: str,
    top_k: int | None = None,
    *,
    experience_min: float | None = None,
    hard_requirements: list[str] | None = None,
) -> list[dict]:
    """Combines pgvector dense similarity with Postgres full-text keyword rank,
    after a cheap SQL pre-filter removes candidates who can't plausibly pass
    regardless of embedding similarity.

    The pre-filter runs before any vector math so it costs an index lookup,
    not a table scan: it never rejects a candidate outright on missing data
    (no profile extracted yet, experience not captured) — it only excludes
    candidates whose *known* values clearly fall outside the JD's hard floor.
    That keeps recall safe while still shrinking the pool that gets ranked and,
    downstream, scored by the LLM. See project doc, Section 8.4 for the fusion
    formula and Section 4.2 for how this fits into the matching pipeline.
    """
    k = top_k or settings.default_top_k
    hard_requirements = [h.strip() for h in (hard_requirements or []) if h and h.strip()]
    min_experience = max(0.0, (experience_min or 0) - EXPERIENCE_FLOOR_BUFFER_YEARS)

    query = text("""
        WITH eligible AS (
            SELECT cp.candidate_id
            FROM candidate_profiles cp
            JOIN candidates c ON c.id = cp.candidate_id
            WHERE c.status = 'ready'
              AND c.deleted_at IS NULL
              -- Experience floor: unknown (NULL) experience is never excluded,
              -- only a known value below the floor is.
              AND (cp.total_experience_years IS NULL OR cp.total_experience_years >= :min_experience)
              -- Hard requirements: every must-have term has to appear
              -- somewhere in the extracted skills or work history. An empty
              -- hard_requirements list matches everyone (no-op filter).
              AND (
                  :hard_requirements_count = 0
                  OR NOT EXISTS (
                      SELECT 1 FROM unnest(CAST(:hard_requirements AS text[])) AS req
                      WHERE NOT (
                          (cp.skills::text || ' ' || cp.work_history::text) ILIKE '%' || req || '%'
                      )
                  )
              )
        )
        SELECT
            ce.candidate_id,
            (:dense_weight * (1 - (ce.embedding <=> CAST(:query_vector AS vector))))
            + (:keyword_weight * COALESCE(
                ts_rank(to_tsvector('english', cp.skills::text), plainto_tsquery('english', :keywords)),
                0
              )) AS combined_score
        FROM candidate_embeddings ce
        JOIN candidate_profiles cp ON cp.candidate_id = ce.candidate_id
        JOIN eligible ON eligible.candidate_id = ce.candidate_id
        ORDER BY combined_score DESC
        LIMIT :top_k
    """)

    result = await db.execute(
        query,
        {
            "query_vector": query_embedding,
            "keywords": query_keywords,
            "dense_weight": settings.hybrid_dense_weight,
            "keyword_weight": settings.hybrid_keyword_weight,
            "top_k": k,
            "min_experience": min_experience,
            "hard_requirements": hard_requirements,
            "hard_requirements_count": len(hard_requirements),
        },
    )
    return [{"candidate_id": row.candidate_id, "score": row.combined_score} for row in result]
