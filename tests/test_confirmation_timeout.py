"""Broker de confirmação expõe timeout_seconds no evento."""

import threading

from nullain.server import ConfirmationBroker


def test_confirmation_request_includes_timeout_seconds():
    broker = ConfirmationBroker(timeout_seconds=42)
    events: list[dict] = []

    def send_event(event: dict) -> None:
        events.append(event)
        # Responde em thread auxiliar: request() segura o gate até o wait terminar.
        request_id = event["request_id"]
        threading.Thread(
            target=lambda: broker.respond(request_id, True),
            daemon=True,
        ).start()

    approved = broker.request("preview", send_event)

    assert approved is True
    assert len(events) == 1
    assert events[0]["type"] == "confirmation_request"
    assert events[0]["timeout_seconds"] == 42
    assert events[0]["preview"] == "preview"
