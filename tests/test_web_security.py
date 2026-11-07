from __future__ import annotations

import http.client
import inspect
import json
import threading
from pathlib import Path

import pytest

from tradinglab import web
from tradinglab.config import Settings


def _data(tmp_path: Path) -> web.LabData:
    return web.LabData(
        Settings(),
        root=tmp_path,
        db_path=tmp_path / "missing.db",
        external=False,
    )


@pytest.fixture()
def server(tmp_path: Path):
    instance = web.DashboardServer(("127.0.0.1", 0), _data(tmp_path))
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def _request(
    server: web.DashboardServer,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    sent = dict(headers or {})
    if payload is not None:
        sent.setdefault("Content-Type", "application/json")
        sent["Content-Length"] = str(len(payload))
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=5
    )
    try:
        connection.request(method, path, body=payload, headers=sent)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw or b"{}")
    finally:
        connection.close()


def _token(server: web.DashboardServer) -> str:
    status, payload = _request(server, "GET", "/api/session")
    assert status == 200
    assert payload["csrf"]
    return payload["csrf"]


def test_session_entrega_token_y_host_local(server) -> None:
    status, health = _request(server, "GET", "/api/health")
    assert status == 200 and health["ok"] is True
    token = _token(server)
    assert len(token) >= 32
    assert token == _token(server)  # estable dentro del proceso


def test_host_no_local_se_rechaza(server) -> None:
    status, payload = _request(
        server, "GET", "/api/health", headers={"Host": "evil.example"}
    )
    assert status == 403
    assert "Host" in payload["error"]
    status, _ = _request(
        server, "GET", "/api/session", headers={"Host": "localhost:8420"}
    )
    assert status == 403


def test_post_sin_token_es_403_y_no_lanza_accion(server) -> None:
    status, payload = _request(server, "POST", "/api/actions/dryrun", body={})
    assert status == 403
    assert "CSRF" in payload["error"]
    assert server.data.action_status() == {"status": "idle"}


def test_post_con_token_incorrecto_es_403(server) -> None:
    status, _ = _request(
        server,
        "POST",
        "/api/bots/archive",
        body={},
        headers={"X-CSRF-Token": "no-es-el-token"},
    )
    assert status == 403


def test_origin_externo_se_rechaza_aunque_el_token_sea_valido(server) -> None:
    status, payload = _request(
        server,
        "POST",
        "/api/bots/archive",
        body={},
        headers={"X-CSRF-Token": _token(server), "Origin": "http://evil.example"},
    )
    assert status == 403
    assert "Origin" in payload["error"]


def test_host_externo_se_rechaza_incluso_con_token(server) -> None:
    status, _ = _request(
        server,
        "POST",
        "/api/bots/archive",
        body={},
        headers={"X-CSRF-Token": _token(server), "Host": "evil.example"},
    )
    assert status == 403


def test_token_valido_llega_al_endpoint(server) -> None:
    status, payload = _request(
        server,
        "POST",
        "/api/bots/archive",
        body={},
        headers={"X-CSRF-Token": _token(server), "Origin": "http://127.0.0.1:8420"},
    )
    assert status == 400
    assert payload["error"] == "Falta id"


def test_rutas_de_escritura_son_lista_blanca(server) -> None:
    assert set(web.WRITE_ROUTES) == {
        "/api/actions/dryrun",
        "/api/actions/agent",
        "/api/bots/evaluate",
        "/api/bots/archive",
        "/api/bots/restore",
        "/api/bots/propose",
    }
    for route in web.WRITE_ROUTES:
        lowered = route.lower()
        for forbidden in ("enable", "order", "firm", "prop.yaml"):
            assert forbidden not in lowered


def test_consola_no_puede_activar_bots_ni_enviar_ordenes() -> None:
    source = inspect.getsource(web.DashboardHandler)
    for forbidden in (
        "set_enabled",
        "enabled =",
        "enabled=",
        "place_order",
        "submit_order",
        "send_order",
        "prop.yaml",
        "from_yaml(",
    ):
        assert forbidden not in source
    text = web.INDEX_FILE.read_text(encoding="utf-8")
    assert '"/api/session"' in text
    assert "X-CSRF-Token" in text
