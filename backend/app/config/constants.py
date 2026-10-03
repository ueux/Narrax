"""Constants that both the schema and the intelligence layer must agree on.

These live in `config/` (a leaf package) so that ORM models, migrations, and analysis code
all import one definition rather than repeating a magic number.
"""

# Output dimensionality of the MVP embedding model. The `embeddings.embedding` column is
# `vector(EMBEDDING_DIMENSIONS)`, so changing to a model with a different dimensionality
# requires a migration (see docs/database.md, "pgvector usage").
EMBEDDING_DIMENSIONS = 384
