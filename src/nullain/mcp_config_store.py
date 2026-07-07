import json
from pathlib import Path
from typing import Any

from nullain.mcp_client import CONFIG_PATH


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"servers": []}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def list_servers() -> list[dict[str, Any]]:
    return load_config().get("servers", [])


def get_server(name: str) -> dict[str, Any] | None:
    for server in list_servers():
        if server.get("name") == name:
            return server
    return None


def add_server(server: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    servers = config.setdefault("servers", [])

    if any(item.get("name") == server.get("name") for item in servers):
        raise ValueError(f"Servidor já existe: {server.get('name')}")

    servers.append(server)
    save_config(config)
    return server


def delete_server(name: str) -> bool:
    config = load_config()
    servers = config.get("servers", [])
    filtered = [server for server in servers if server.get("name") != name]

    if len(filtered) == len(servers):
        return False

    config["servers"] = filtered
    save_config(config)
    return True