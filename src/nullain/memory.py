from __future__ import annotations

import json
import queue
import struct
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3

import sqlite_vec

from nullain.embeddings import EmbeddingUnavailable, embed_text

DB_PATH = Path("nullain.db")
_VEC_TABLE = "vec_facts"
_EMBED_DIM_KEY = "embed_dim"
VEC_AVAILABLE = False

_WAL_ENABLED = False
_BG_QUEUE: queue.Queue | None = None
_BG_THREAD: threading.Thread | None = None
_BG_STOP = threading.Event()


@dataclass
class Fact:
    id: int
    key: str
    value: str
    created_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _load_vec_extension(conn: sqlite3.Connection) -> None:
    global VEC_AVAILABLE

    if not hasattr(conn, "enable_load_extension"):
        VEC_AVAILABLE = False
        return

    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        VEC_AVAILABLE = True
    except Exception:
        VEC_AVAILABLE = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if _WAL_ENABLED:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
    _load_vec_extension(conn)
    return conn


def _enable_wal() -> None:
    global _WAL_ENABLED
    try:
        with _connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        _WAL_ENABLED = True
    except Exception:
        _WAL_ENABLED = False


def _get_embed_dim(conn: sqlite3.Connection | None = None) -> int | None:
    if conn is None:
        raw = get_setting(_EMBED_DIM_KEY)
        return int(raw) if raw else None

    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (_EMBED_DIM_KEY,),
    ).fetchone()
    return int(row["value"]) if row else None


def _set_embed_dim(conn: sqlite3.Connection, dim: int) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_EMBED_DIM_KEY, str(dim)),
    )


def _drop_vec_table(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {_VEC_TABLE}")


def _create_vec_table(conn: sqlite3.Connection, dim: int) -> None:
    conn.execute(f"CREATE VIRTUAL TABLE {_VEC_TABLE} USING vec0(embedding float[{dim}])")
    _set_embed_dim(conn, dim)


def _vec_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = ?",
        (_VEC_TABLE,),
    ).fetchone()
    return row is not None


def _facts_missing_embeddings(conn: sqlite3.Connection) -> list[Fact]:
    if not VEC_AVAILABLE:
        return []

    if not _vec_table_exists(conn):
        rows = conn.execute(
            "SELECT id, key, value, created_at FROM facts ORDER BY id ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT f.id, f.key, f.value, f.created_at
            FROM facts f
            LEFT JOIN {_VEC_TABLE} v ON v.rowid = f.id
            WHERE v.rowid IS NULL
            ORDER BY f.id ASC
            """
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


def _store_fact_embedding(conn: sqlite3.Connection, fact_id: int, vector: list[float]) -> None:
    if not VEC_AVAILABLE:
        return

    dim = len(vector)
    stored_dim = _get_embed_dim(conn)

    if stored_dim is None:
        _create_vec_table(conn, dim)
    elif stored_dim != dim:
        _recreate_vec_table(conn, dim)
        facts = conn.execute(
            "SELECT id, key, value, created_at FROM facts ORDER BY id ASC"
        ).fetchall()
        for row in facts:
            if row["id"] == fact_id:
                continue
            try:
                other_vector = embed_text(row["value"])
            except EmbeddingUnavailable:
                continue
            except Exception:
                continue
            if len(other_vector) == dim:
                conn.execute(
                    f"INSERT INTO {_VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
                    (row["id"], _serialize_f32(other_vector)),
                )

    conn.execute(
        f"INSERT OR REPLACE INTO {_VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
        (fact_id, _serialize_f32(vector)),
    )


def _recreate_vec_table(conn: sqlite3.Connection, dim: int) -> None:
    _drop_vec_table(conn)
    _create_vec_table(conn, dim)


def _has_vector_index() -> bool:
    if not VEC_AVAILABLE:
        return False

    with _connect() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (_VEC_TABLE,),
        ).fetchone()
        if row is None:
            return False
        count = conn.execute(f"SELECT COUNT(*) AS total FROM {_VEC_TABLE}").fetchone()
        return bool(count and count["total"] > 0)


def init_db() -> None:
    _enable_wal()

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

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages (session_id);

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

            CREATE INDEX IF NOT EXISTS idx_tool_logs_session
                ON tool_logs (session_id);

            CREATE INDEX IF NOT EXISTS idx_tool_logs_created
                ON tool_logs (created_at);

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn_index INTEGER NOT NULL,
                ttft_ms REAL,
                total_ms REAL NOT NULL,
                iterations INTEGER NOT NULL DEFAULT 0,
                tokens_in INTEGER,
                tokens_out INTEGER,
                tool_count INTEGER NOT NULL DEFAULT 0,
                tool_total_ms REAL NOT NULL DEFAULT 0,
                model TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_session
                ON metrics (session_id);

            CREATE INDEX IF NOT EXISTS idx_metrics_created
                ON metrics (created_at);
            """
        )

    start_background_writer()
    try:
        purge_retention()
    except Exception:
        pass
    backfill_pending_embeddings_background()


def backfill_pending_embeddings() -> None:
    try:
        with _connect() as conn:
            pending = _facts_missing_embeddings(conn)
            for fact in pending:
                try:
                    vector = embed_text(fact.value)
                except EmbeddingUnavailable:
                    return
                except Exception:
                    continue
                _store_fact_embedding(conn, fact.id, vector)
    except Exception:
        return


def backfill_pending_embeddings_background() -> None:
    enqueue_background(backfill_pending_embeddings)


def start_background_writer() -> None:
    global _BG_QUEUE, _BG_THREAD

    if _BG_THREAD is not None and _BG_THREAD.is_alive():
        return

    if _BG_QUEUE is None:
        _BG_QUEUE = queue.Queue()

    _BG_STOP.clear()

    def _worker() -> None:
        while not _BG_STOP.is_set():
            try:
                task = _BG_QUEUE.get(timeout=0.5)
            except queue.Empty:
                continue
            if task is None:
                break
            fn, args = task
            try:
                fn(*args)
            except Exception:
                pass

    _BG_THREAD = threading.Thread(target=_worker, daemon=True)
    _BG_THREAD.start()


def stop_background_writer() -> None:
    global _BG_QUEUE, _BG_THREAD
    _BG_STOP.set()
    if _BG_QUEUE is not None:
        _BG_QUEUE.put(None)
    if _BG_THREAD is not None:
        _BG_THREAD.join(timeout=2)
    _BG_QUEUE = None
    _BG_THREAD = None


def enqueue_background(fn, *args) -> None:
    if _BG_QUEUE is not None:
        _BG_QUEUE.put((fn, args))
    else:
        try:
            fn(*args)
        except Exception:
            pass


def flush_background_writer(timeout: float = 5.0) -> None:
    """Bloqueia até esvaziar a fila (tarefas enfileiradas antes do marker)."""
    if _BG_QUEUE is None:
        return

    done = threading.Event()

    def _mark_done() -> None:
        done.set()

    _BG_QUEUE.put((_mark_done, ()))
    if not done.wait(timeout=timeout):
        raise TimeoutError(
            f"flush_background_writer: fila não esvaziou em {timeout}s"
        )


@dataclass
class TurnMetrics:
    session_id: str | None = None
    turn_index: int = 0
    ttft_ms: float | None = None
    total_ms: float = 0.0
    iterations: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    tool_count: int = 0
    tool_total_ms: float = 0.0
    model: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def log_turn_metrics(metrics: TurnMetrics) -> None:
    enqueue_background(_log_turn_metrics_sync, metrics)


def _log_turn_metrics_sync(metrics: TurnMetrics) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO metrics (
                session_id, turn_index, ttft_ms, total_ms, iterations,
                tokens_in, tokens_out, tool_count, tool_total_ms, model, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metrics.session_id,
                metrics.turn_index,
                metrics.ttft_ms,
                metrics.total_ms,
                metrics.iterations,
                metrics.tokens_in,
                metrics.tokens_out,
                metrics.tool_count,
                metrics.tool_total_ms,
                metrics.model,
                metrics.created_at,
            ),
        )


def get_metrics(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, turn_index, ttft_ms, total_ms, iterations, "
            "tokens_in, tokens_out, tool_count, tool_total_ms, model, created_at "
            "FROM metrics ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_metric_percentiles(field: str = "ttft_ms", limit: int = 100) -> dict[str, float | None]:
    if field not in ("ttft_ms", "total_ms", "tool_total_ms"):
        field = "ttft_ms"

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {field} AS value FROM metrics "
            f"WHERE {field} IS NOT NULL "
            f"ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    values = [float(row["value"]) for row in rows if row["value"] is not None]
    if not values:
        return {"p50": None, "p90": None, "p95": None, "p99": None, "count": 0}

    def percentile(data: list[float], pct: float) -> float:
        sorted_data = sorted(data)
        index = max(0, min(len(sorted_data) - 1, int(len(sorted_data) * pct / 100)))
        return sorted_data[index]

    return {
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "count": len(values),
    }


def list_sessions(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT session_id,
                   MIN(created_at) AS first_at,
                   MAX(created_at) AS last_at,
                   COUNT(*) AS message_count,
                   SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) AS user_count
            FROM messages
            GROUP BY session_id
            ORDER BY last_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, created_at "
            "FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def add_message(session_id: str, role: str, content: str) -> None:
    enqueue_background(_add_message_sync, session_id, role, content)


def _add_message_sync(session_id: str, role: str, content: str) -> None:
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

        try:
            vector = embed_text(value)
        except EmbeddingUnavailable:
            vector = None
        except Exception:
            vector = None
        else:
            _store_fact_embedding(conn, fact_id, vector)

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


def search_facts(query: str, top_k: int = 5) -> list[Fact]:
    if not query.strip() or not _has_vector_index():
        return []

    try:
        vector = embed_text(query)
    except EmbeddingUnavailable:
        return []

    stored_dim = _get_embed_dim()
    if stored_dim is None or stored_dim != len(vector):
        return []

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT f.id, f.key, f.value, f.created_at
            FROM {_VEC_TABLE} v
            JOIN facts f ON f.id = v.rowid
            WHERE v.embedding MATCH ?
            AND k = ?
            ORDER BY distance
            """,
            (_serialize_f32(vector), top_k),
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
        if VEC_AVAILABLE:
            conn.execute(f"DELETE FROM {_VEC_TABLE} WHERE rowid = ?", (fact_id,))
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
    enqueue_background(_log_tool_call_sync, tool_name, arguments, result, session_id)


def _log_tool_call_sync(
    tool_name: str,
    arguments: dict,
    result: str,
    session_id: str | None = None,
) -> None:
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


def purge_retention(
    *,
    log_retention_days: int | None = None,
    log_max_rows: int | None = None,
    metrics_retention_days: int | None = None,
    metrics_max_rows: int | None = None,
) -> dict[str, int]:
    """Remove tool_logs e metrics antigos/excedentes. Retorna contagens deletadas."""
    try:
        from nullain.config import get_settings

        settings = get_settings()
        if log_retention_days is None:
            log_retention_days = int(settings.nullain_log_retention_days)
        if log_max_rows is None:
            log_max_rows = int(settings.nullain_log_max_rows)
        if metrics_retention_days is None:
            metrics_retention_days = int(settings.nullain_metrics_retention_days)
        if metrics_max_rows is None:
            metrics_max_rows = int(settings.nullain_metrics_max_rows)
    except Exception:
        log_retention_days = log_retention_days if log_retention_days is not None else 30
        log_max_rows = log_max_rows if log_max_rows is not None else 5000
        metrics_retention_days = (
            metrics_retention_days if metrics_retention_days is not None else 30
        )
        metrics_max_rows = metrics_max_rows if metrics_max_rows is not None else 5000

    deleted = {"tool_logs": 0, "metrics": 0}
    now = datetime.now(timezone.utc)

    with _connect() as conn:
        if log_retention_days and log_retention_days > 0:
            cutoff = (now - timedelta(days=log_retention_days)).isoformat()
            cur = conn.execute("DELETE FROM tool_logs WHERE created_at < ?", (cutoff,))
            deleted["tool_logs"] += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

        if log_max_rows and log_max_rows > 0:
            cur = conn.execute(
                """
                DELETE FROM tool_logs
                WHERE id NOT IN (
                    SELECT id FROM tool_logs ORDER BY id DESC LIMIT ?
                )
                """,
                (log_max_rows,),
            )
            deleted["tool_logs"] += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

        if metrics_retention_days and metrics_retention_days > 0:
            cutoff = (now - timedelta(days=metrics_retention_days)).isoformat()
            cur = conn.execute("DELETE FROM metrics WHERE created_at < ?", (cutoff,))
            deleted["metrics"] += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

        if metrics_max_rows and metrics_max_rows > 0:
            cur = conn.execute(
                """
                DELETE FROM metrics
                WHERE id NOT IN (
                    SELECT id FROM metrics ORDER BY id DESC LIMIT ?
                )
                """,
                (metrics_max_rows,),
            )
            deleted["metrics"] += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    return deleted


def get_tool_logs(limit: int = 50) -> list[dict]:
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


def format_facts_for_prompt(query: str | None = None) -> str:
    facts: list[Fact]

    if query and query.strip() and _has_vector_index():
        try:
            facts = search_facts(query, top_k=5)
        except EmbeddingUnavailable:
            facts = list_facts()
        except Exception:
            facts = list_facts()
        if not facts:
            facts = list_facts()
    else:
        facts = list_facts()

    if not facts:
        return ""

    lines = [f"- {fact.value}" for fact in facts]
    return "Fatos conhecidos sobre Netty:\n" + "\n".join(lines)


def fact_has_embedding(fact_id: int) -> bool:
    if not VEC_AVAILABLE:
        return False

    with _connect() as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (_VEC_TABLE,),
        ).fetchone()
        if table is None:
            return False
        row = conn.execute(
            f"SELECT rowid FROM {_VEC_TABLE} WHERE rowid = ?",
            (fact_id,),
        ).fetchone()
    return row is not None