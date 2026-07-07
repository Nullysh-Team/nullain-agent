import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("nullain.db")


@dataclass
class Fact:
    id: int
    key: str
    value: str
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                arguments TEXT NOT NULL,
                result TEXT NOT NULL,
                session_id TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


def add_message(session_id: str, role: str, content: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now_iso()),
        )


def add_fact(value: str) -> Fact:
    key = value[:100]
    created_at = _now_iso()

    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO facts (key, value, created_at) VALUES (?, ?, ?)",
            (key, value, created_at),
        )
        fact_id = int(cursor.lastrowid)

    return Fact(id=fact_id, key=key, value=value, created_at=created_at)


def list_facts() -> list[Fact]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, key, value, created_at FROM facts ORDER BY id ASC"
        ).fetchall()

    return [
        Fact(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def delete_fact(fact_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        return cursor.rowcount > 0


def get_setting(key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_runtime_config() -> dict[str, str | float | None]:
    temperature_raw = get_setting("temperature")
    temperature = float(temperature_raw) if temperature_raw is not None else None
    return {
        "model": get_setting("model"),
        "temperature": temperature,
        "system_prompt": get_setting("system_prompt"),
    }


def update_runtime_config(
    *,
    model: str | None = None,
    temperature: float | None = None,
    system_prompt: str | None = None,
) -> dict[str, str | float | None]:
    if model is not None:
        set_setting("model", model)
    if temperature is not None:
        set_setting("temperature", str(temperature))
    if system_prompt is not None:
        set_setting("system_prompt", system_prompt)
    return get_runtime_config()


def log_tool_call(
    tool_name: str,
    arguments: dict,
    result: str,
    session_id: str | None = None,
) -> None:
    import json

    with _connect() as conn:
        conn.execute(
            "INSERT INTO tool_logs (tool_name, arguments, result, session_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                result,
                session_id,
                _now_iso(),
            ),
        )


def get_tool_logs(limit: int = 50) -> list[dict]:
    import json

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, tool_name, arguments, result, session_id, created_at "
            "FROM tool_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "tool_name": row["tool_name"],
            "arguments": json.loads(row["arguments"]),
            "result": row["result"],
            "session_id": row["session_id"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def format_facts_for_prompt() -> str:
    facts = list_facts()
    if not facts:
        return ""

    lines = [f"- {fact.value}" for fact in facts]
    return "Fatos conhecidos sobre Netty:\n" + "\n".join(lines)