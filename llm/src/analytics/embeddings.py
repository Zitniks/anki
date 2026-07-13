"""Sentence embeddings using sentence-transformers.

Model: multilingual-e5-small
  - 384 dimensions (same as the previous multi-qa-MiniLM-L6-cos-v1 — no schema change)
  - Switched from multi-qa-MiniLM-L6-cos-v1 after scripts/eval_rag.py showed
    38.5% Recall@5 on the real eval set (target >=85%, see tz_rag_agent.md
    §8.2) — almost every miss was a purely-Russian query (no English anchor
    term) scoring below _MIN_VECTOR_SCORE against the English-only corpus.
    multi-qa-MiniLM-L6-cos-v1 isn't multilingual; this model is trained for
    cross-lingual retrieval and scored recall@5=76.9%/MRR=0.593 vs this
    project's real 130-query eval set (offline, same corpus) vs 66.2%/0.451
    for the old model — verified before switching, not a guess.
  - E5 models are trained with "query: "/"passage: " instruction prefixes —
    embed()/embed_batch() apply these automatically via `is_query`. Skipping
    them measurably hurts retrieval quality for E5-family models.
  - Runs on CPU, no GPU needed

The model is loaded once and cached for the process lifetime.
First call triggers HuggingFace download.

Existing rows embedded with a previous model must be re-indexed (POST
/rag/reindex with corpus=exercise|example|explanation and force=true) —
vectors from different models aren't comparable in the same column.
"""

from functools import lru_cache
from typing import Any

MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIM = 384

# E5-family models expect "query: " / "passage: " prefixes on their input —
# without them the model still runs, but retrieval quality drops. Other model
# families (e.g. the previous multi-qa-MiniLM-L6-cos-v1) don't use this
# convention, so prefixing is gated on the active model.
_USES_E5_PREFIXES = MODEL_NAME.startswith("intfloat/e5-") or MODEL_NAME.startswith("intfloat/multilingual-e5-")


@lru_cache(maxsize=1)
def _model() -> Any:
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def _prefix(text: str, is_query: bool) -> str:
    if not _USES_E5_PREFIXES:
        return text
    return f"query: {text}" if is_query else f"passage: {text}"


def embed(text: str, is_query: bool = False) -> list[float]:
    """Embed a single text string into a 384-dim vector.

    Parameters
    ----------
    text : str
        Text to embed (will be truncated to 256 tokens by the model).
    is_query : bool
        True when embedding a search query, False when embedding a corpus
        document to index. Matters for E5-family models (see module docstring);
        no-op for other model families.

    Returns
    -------
    list[float]
        Unit-normalised embedding vector of length 384.
    """
    vec = _model().encode(_prefix(text, is_query), normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """Embed multiple texts in one forward pass (faster than calling embed() in a loop).

    Parameters
    ----------
    texts : list[str]
        Texts to embed.
    is_query : bool
        See `embed`.

    Returns
    -------
    list[list[float]]
        List of 384-dim unit-normalised vectors.
    """
    prefixed = [_prefix(t, is_query) for t in texts]
    vecs = _model().encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def material_text(name: str, content: str, tags: list[str] | None = None) -> str:
    """Compose the text to embed for a material.

    Combines name (most important), tags, and content so the vector
    captures both the topic label and the exercise text.
    """
    parts = [name]
    if tags:
        parts.append(" ".join(tags))
    if content:
        parts.append(content[:512])   # truncate long exercises
    return " | ".join(parts)
