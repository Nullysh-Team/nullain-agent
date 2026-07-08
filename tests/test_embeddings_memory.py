import pytest

from nullain.embeddings import EmbeddingUnavailable
from nullain import memory


@pytest.fixture
def mem_db(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "memory.db")
    memory.init_db()
    yield


def _vector_for_text(text: str, dim: int = 4) -> list[float]:
    base = [0.0] * dim
    token = text.lower()
    if "pizza" in token:
        base[0] = 1.0
    elif "sushi" in token:
        base[1] = 1.0
    elif "python" in token:
        base[2] = 1.0
    else:
        base[3] = 1.0
    return base


def test_search_facts_returns_top_k_in_expected_order(mem_db, monkeypatch):
    current_dim = {"value": 4}

    def fake_embed(text: str) -> list[float]:
        return _vector_for_text(text, current_dim["value"])

    monkeypatch.setattr(memory, "embed_text", fake_embed)

    memory.add_fact("Netty adora pizza")
    memory.add_fact("Netty prefere sushi")
    memory.add_fact("Netty programa em Python")

    results = memory.search_facts("pergunta sobre pizza", top_k=2)

    assert len(results) == 2
    assert "pizza" in results[0].value.lower()
    assert results[0].id != results[1].id


def test_add_fact_survives_embedding_unavailable(mem_db, monkeypatch):
    def unavailable(_text: str) -> list[float]:
        raise EmbeddingUnavailable("ollama offline")

    monkeypatch.setattr(memory, "embed_text", unavailable)

    fact = memory.add_fact("Fato sem embedding")

    assert fact.id > 0
    assert memory.list_facts()[0].value == "Fato sem embedding"
    assert memory.fact_has_embedding(fact.id) is False


def test_format_facts_for_prompt_falls_back_without_embeddings(mem_db, monkeypatch):
    def unavailable(_text: str) -> list[float]:
        raise EmbeddingUnavailable("ollama offline")

    monkeypatch.setattr(memory, "embed_text", unavailable)

    memory.add_fact("Fato A")
    memory.add_fact("Fato B")

    prompt = memory.format_facts_for_prompt(query="consulta qualquer")

    assert "Fato A" in prompt
    assert "Fato B" in prompt


def test_dimension_change_reembeds_without_crash(mem_db, monkeypatch):
    current_dim = {"value": 4}

    def fake_embed(text: str) -> list[float]:
        return _vector_for_text(text, current_dim["value"])

    monkeypatch.setattr(memory, "embed_text", fake_embed)

    first = memory.add_fact("Netty adora pizza")
    assert memory.fact_has_embedding(first.id) is True
    assert memory.get_setting("embed_dim") == "4"

    current_dim["value"] = 8
    second = memory.add_fact("Netty prefere sushi")

    assert memory.fact_has_embedding(second.id) is True
    assert memory.get_setting("embed_dim") == "8"
    assert memory.fact_has_embedding(first.id) is True

    results = memory.search_facts("sushi", top_k=1)
    assert len(results) == 1
    assert "sushi" in results[0].value.lower()