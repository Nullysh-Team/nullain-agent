import litellm
import pytest
from litellm.exceptions import AuthenticationError, RateLimitError

from nullain import llm, memory


@pytest.fixture(autouse=True)
def _test_db(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "test.db")
    memory.init_db()


class _FakeMessage:
    def __init__(self, content: str = "ok") -> None:
        self.content = content
        self.tool_calls = None


class _FakeChoice:
    def __init__(self, content: str = "ok") -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str = "ok") -> None:
        self.choices = [_FakeChoice(content)]


def test_complete_retries_transient_errors(monkeypatch):
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_completion(**kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise RateLimitError(
                message="rate limited",
                llm_provider="test",
                model="test-model",
            )
        return _FakeResponse("sucesso")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(llm.random, "uniform", lambda _a, _b: 0.25)

    response = llm.complete(
        [{"role": "user", "content": "oi"}],
        model="test-model",
        temperature=0.0,
    )

    assert response.choices[0].message.content == "sucesso"
    assert calls["count"] == 3
    assert sleeps == [1.25, 2.25]


def test_complete_does_not_retry_authentication_error(monkeypatch):
    calls = {"count": 0}

    def fake_completion(**kwargs):
        calls["count"] += 1
        raise AuthenticationError(
            message="invalid key",
            llm_provider="test",
            model="test-model",
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(
        llm.time,
        "sleep",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("sleep não deve ser chamado")
        ),
    )

    with pytest.raises(AuthenticationError):
        llm.complete(
            [{"role": "user", "content": "oi"}],
            model="test-model",
            temperature=0.0,
        )

    assert calls["count"] == 1