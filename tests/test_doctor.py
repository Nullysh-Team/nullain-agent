import builtins
import io
import sys
from pathlib import Path

from rich.console import Console


def _import_doctor_without_sounddevice():
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sounddevice":
            raise OSError("PortAudio library not found")
        return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = guarded_import
    sys.modules.pop("nullain.doctor", None)
    from nullain import doctor, memory

    builtins.__import__ = real_import
    return doctor, memory


doctor, memory = _import_doctor_without_sounddevice()


def test_run_checks_handles_checker_exception(monkeypatch):
    def boom() -> doctor.CheckResult:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(doctor, "_check_python", boom)

    results = doctor.run_checks()
    python_result = next(result for result in results if result.name == "Python >= 3.13")

    assert python_result.ok is False
    assert "falha simulada" in python_result.detail


def test_sqlite_check_uses_isolated_temp_database(monkeypatch, tmp_path):
    real_db = tmp_path / "real-nullain.db"
    monkeypatch.setattr(memory, "DB_PATH", real_db)

    touched: list[Path] = []
    original_connect = doctor.sqlite3.connect

    def tracking_connect(database, *args, **kwargs):
        touched.append(Path(database))
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(doctor.sqlite3, "connect", tracking_connect)

    result = doctor._check_sqlite()

    assert result.ok is True
    assert result.detail == "leitura/escrita OK"
    assert touched
    assert all(path != real_db for path in touched)
    assert not real_db.exists()


def test_optional_tokens_are_informational_and_excluded_from_score(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("GROQ_API_KEY=valor\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "ENV_PATH", env_path)

    monkeypatch.setattr(doctor, "_check_python", lambda: doctor.CheckResult("Python >= 3.13", True, "3.13.0"))
    monkeypatch.setattr(doctor, "_check_env_file", lambda: doctor.CheckResult(".env existe", True, "ok"))
    monkeypatch.setattr(doctor, "_check_active_model", lambda: doctor.CheckResult("Modelo ativo", True, "m"))
    monkeypatch.setattr(doctor, "_check_ollama", lambda: doctor.CheckResult("Ollama local", True, "ok"))
    monkeypatch.setattr(doctor, "_check_piper_model", lambda: doctor.CheckResult("Modelo Piper", True, "ok"))
    monkeypatch.setattr(doctor, "_check_sqlite", lambda: doctor.CheckResult("Banco SQLite", True, "ok"))
    monkeypatch.setattr(
        doctor,
        "_check_semantic_search",
        lambda: doctor.CheckResult("Busca semântica", True, "ativa (sqlite-vec + m)", mandatory=False),
    )
    monkeypatch.setattr(doctor, "_check_mcp_config", lambda: doctor.CheckResult("mcp.config.json", True, "ok"))
    monkeypatch.setattr(doctor, "_check_port", lambda: doctor.CheckResult("Porta 8420", True, "livre"))

    results = doctor.run_checks()

    openai = next(result for result in results if result.name == "Token OPENAI_API_KEY")
    groq = next(result for result in results if result.name == "Token GROQ_API_KEY")

    assert doctor.status_mark(openai) == "—"
    assert openai.detail == "—"
    assert openai.mandatory is False
    assert doctor.status_mark(groq) == "✓"
    assert groq.detail == "presente"

    ok_count, total = doctor.score_summary(results)
    assert total == 8
    assert ok_count == 8
    assert "Token OPENAI_API_KEY" not in {r.name for r in results if r.mandatory}


def test_semantic_search_check_reports_active_and_inactive_states(monkeypatch):
    class _Settings:
        nullain_embed_model = "ollama/nomic-embed-text"

    monkeypatch.setattr("nullain.config.get_settings", lambda: _Settings())
    monkeypatch.setattr(memory, "VEC_AVAILABLE", True)
    monkeypatch.setattr(memory, "list_facts", lambda: [])
    monkeypatch.setattr(memory, "fact_has_embedding", lambda _fact_id: True)

    active = doctor._check_semantic_search()
    assert active.detail.startswith("ativa (sqlite-vec +")
    assert doctor.status_mark(active) == "✓"

    monkeypatch.setattr(memory, "VEC_AVAILABLE", False)
    inactive = doctor._check_semantic_search()
    assert inactive.detail == "inativa: sqlite-vec indisponível"
    assert doctor.status_mark(inactive) == "—"


def test_doctor_report_never_exposes_token_values(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    secret = "sk-super-secreto-nao-pode-vazar"
    env_path.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")

    monkeypatch.setattr(doctor, "ENV_PATH", env_path)
    monkeypatch.setattr(doctor, "_check_ollama", lambda: doctor.CheckResult("Ollama local", True, "ok", ""))
    monkeypatch.setattr(
        doctor,
        "_check_piper_model",
        lambda: doctor.CheckResult("Modelo Piper", True, "models/test.onnx", ""),
    )
    monkeypatch.setattr(
        doctor,
        "_check_mcp_config",
        lambda: doctor.CheckResult("mcp.config.json", True, "test", ""),
    )

    results = doctor.run_checks()
    report = doctor.format_doctor_report(results)

    assert "presente" in report or "—" in report
    assert secret not in report
    assert "sk-" not in report

    console = Console(file=io.StringIO(), width=120)
    table_output = io.StringIO()
    console.file = table_output
    for result in results:
        console.print(f"{result.name}: {result.detail}")

    rendered = table_output.getvalue()
    assert secret not in rendered