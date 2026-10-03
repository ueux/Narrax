"""ORM models, grouped by epistemic layer.

Importing this package registers **every** model on `Base.metadata`, which is what Alembic's
`env.py` relies on for autogenerate and what the migration in `alembic/versions/` must match.

```text
account.py      Layer 0   users                      operator identity
topic.py        Layer 1   topics, topic_communities  selection criteria
source.py       Layer 1   sources, communities, authors, discussions
run.py          meta      analysis_runs, run_stages  how outputs were produced
observation.py  Layer 2   discussion_analysis, embeddings, clusters, cluster_members
narrative.py    Layer 3   narratives, narrative_members, narrative_evidence,
                          narrative_relations
temporal.py     Layer 4   narrative_snapshots
```

Explicitly **not** here: business rules (those belong to `services/`) and derived-value
computation (that belongs to `intelligence/`).
"""

from app.database.models.account import User
from app.database.models.narrative import (
    Narrative,
    NarrativeEvidence,
    NarrativeMember,
    NarrativeRelation,
)
from app.database.models.observation import (
    Cluster,
    ClusterMember,
    DiscussionAnalysis,
    Embedding,
)
from app.database.models.preparation import TextPreparation
from app.database.models.run import AnalysisRun, RunStage
from app.database.models.source import Author, Community, Discussion, Source
from app.database.models.temporal import NarrativeSnapshot
from app.database.models.topic import Topic, TopicCommunity

__all__ = [
    # Layer 0 — operator identity
    "User",
    # Layer 1 — source truth
    "Topic",
    "TopicCommunity",
    "Source",
    "Community",
    "Author",
    "Discussion",
    # Run metadata
    "AnalysisRun",
    "RunStage",
    # Layer 2 — ML observations
    "DiscussionAnalysis",
    "TextPreparation",
    "Embedding",
    "Cluster",
    "ClusterMember",
    # Layer 3 — AI interpretations
    "Narrative",
    "NarrativeMember",
    "NarrativeEvidence",
    "NarrativeRelation",
    # Layer 4 — temporal observations
    "NarrativeSnapshot",
]
