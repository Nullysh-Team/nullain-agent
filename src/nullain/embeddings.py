from __future__ import annotations

import litellm

from nullain.config import get_settings


class EmbeddingUnavailable(Exception):
    """Embedding provider indisponível — o chamador deve aplicar fallback."""


def embed_text(text: str) -> list[float]:
    if not text.strip():
        raise EmbeddingUnavailable("texto vazio")

    settings = get_settings()
    try:
        response = litellm.embedding(
            model=settings.nullain_embed_model,
            input=[text],
        )
        embedding = response.data[0]["embedding"]
        if not isinstance(embedding, list) or not embedding:
            raise EmbeddingUnavailable("embedding vazio")
        return [float(value) for value in embedding]
    except EmbeddingUnavailable:
        raise
    except Exception as exc:
        raise EmbeddingUnavailable(str(exc)) from exc