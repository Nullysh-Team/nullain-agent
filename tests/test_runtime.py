import pytest

from nullain.runtime import get_active_temperature


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"temperature": 1}, 1.0),
        ({"temperature": 0.7}, 0.7),
        ({"temperature": True}, None),
        ({"temperature": "0.7"}, None),
        ({}, None),
    ],
)
def test_get_active_temperature(monkeypatch, config, expected):
    monkeypatch.setattr(
        "nullain.runtime.memory.get_runtime_config",
        lambda: config,
    )
    assert get_active_temperature() == expected