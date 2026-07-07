from nullain.config import get_settings
from nullain import memory


def get_active_model() -> str:
    runtime = memory.get_runtime_config()
    model = runtime.get("model")
    if isinstance(model, str) and model.strip():
        return model
    return get_settings().nullain_model


def get_active_temperature() -> float | None:
    runtime = memory.get_runtime_config()
    temperature = runtime.get("temperature")
    return temperature if isinstance(temperature, float) else None