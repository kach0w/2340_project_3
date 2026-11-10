
"""Gemini embedding helpers shared by ingestion and retrieval."""
import functools
import math

from django.conf import settings
from google import genai

EMBEDDING_MODEL = "gemini-embedding-001"


@functools.lru_cache(maxsize=1)
def _client():
    return genai.Client(api_key=settings.GOOGLE_API_KEY)


def embed_text(text, task_type):
    """Return an embedding vector, or None if no API key is configured."""
    if not text or not settings.GOOGLE_API_KEY:
        return None

    result = _client().models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=genai.types.EmbedContentConfig(task_type=task_type),
    )

    if not result.embeddings or not result.embeddings[0].values:
        raise ValueError("Embedding API returned no vector")

    return list(result.embeddings[0].values)


def cosine_similarity(a, b):
    """Calculate similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0

    denominator = (
        math.sqrt(sum(x * x for x in a))
        * math.sqrt(sum(x * x for x in b))
    )

    if denominator == 0:
        return 0.0

    return sum(x * y for x, y in zip(a, b)) / denominator
