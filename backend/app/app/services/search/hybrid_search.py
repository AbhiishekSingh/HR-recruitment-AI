from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


async def hybrid_search(
    db: AsyncSession,
    query_embedding: list[float],
    query_keywords: str,
    top_k: int | None = None,
) -> list[dict]:
    """Combines pgvector dense similarity with Postgres full-text keyword rank.

    See project doc, Section 8.4 for the fusion formula. Weights are configurable
    in settings (HYBRID_DENSE_WEIGHT / HYBRID_KEYWORD_WEIGHT) so they can be tuned
    against the validation set without a code change.
    """
    k = top_k or settings.default_top_k

    query = text("""
        SELECT
            ce.candidate_id,
            (:dense_weight * (1 - (ce.embedding <=> CAST(:query_vector AS vector))))
            + (:keyword_weight * COALESCE(
                ts_rank(to_tsvector('english', cp.skills::text), plainto_tsquery('english', :keywords)),
                0
              )) AS combined_score
        FROM candidate_embeddings ce
        JOIN candidate_profiles cp ON cp.candidate_id = ce.candidate_id
        JOIN candidates c ON c.id = ce.candidate_id
        WHERE c.status = 'ready'
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
        },
    )
    return [{"candidate_id": row.candidate_id, "score": row.combined_score} for row in result]
