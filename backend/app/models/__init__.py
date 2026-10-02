"""ORM models.

Phase 1 (ingestion) will define the source-truth tables here (discussions, comments,
raw content) and Phase 2+ will add the ML-observation tables (embeddings, clusters,
stance, sentiment, narratives). Keeping them in this package lets Alembic autogenerate
migrations from `Base.metadata`.
"""
