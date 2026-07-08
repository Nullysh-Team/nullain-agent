import io

from rich.console import Console

from nullain import doctor, memory


def test_run_checks_handles_checker_exception(monkeypatch):
    def boom() -> doctor.CheckResult:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(doctor, "_check_python", boom)

    results = doctor.run_checks()
    python_result = next(result for result in results if result.name == "Python >= 3.13")

    assert python_result.ok is False
    assert "falha simulada" in python_result.detail


def test_doctor_report_never_exposes_token_values(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    secret = "sk-super-secreto-nao-pode-vazar"
    env_path.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")

    monkeypatch.setattr(doctor, "ENV_PATH", env_path)
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "doctor.db")
    memory.init_db()
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

    assert "presente" in report or "ausente" in report
    assert secret not in report
    assert "sk-" not in report

    console = Console(file=io.StringIO(), width=120)
    table_output = io.StringIO()
    console.file = table_output
    for result in results:
        console.print(f"{result.name}: {result.detail}")

    rendered = table_output.getvalue()
    assert secret not in rendered