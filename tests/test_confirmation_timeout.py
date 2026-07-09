"""Broker de confirmação expõe timeout_seconds no evento."""

from nullain.server import ConfirmationBroker


def test_confirmation_request_includes_timeout_seconds():
    broker = ConfirmationBroker(timeout_seconds=42)
    events: list[dict] = []

    def send_event(event: dict) -> None:
        events.append(event)
        # Responde imediatamente para não bloquear o teste
        request_id = event["request_id"]
        broker.respond(request_id, True)

    approved = broker.request("preview", send_event)

    assert approved is True
    assert len(events) == 1
    assert events[0]["type"] == "confirmation_request"
    assert events[0]["timeout_seconds"] == 42
    assert events[0]["preview"] == "preview"
