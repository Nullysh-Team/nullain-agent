"""Handler de exemplo — sem efeitos colaterais."""


def run(input_text: str = "", confirm=None) -> str:
    text = (input_text or "").strip()
    if not text:
        return "echo: (input vazio)"
    return f"echo: {text.upper()}"
