from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from emergent_rpg.api.app import create_app


def make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "ui.db"))


def test_root_redirects_to_browser_ui(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/ui/"


def test_ui_shell_and_assets_are_served_without_hidden_world_data(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    page = client.get("/ui/")
    script = client.get("/ui/app.js")
    stylesheet = client.get("/ui/styles.css")

    assert page.status_code == 200
    assert script.status_code == 200
    assert stylesheet.status_code == 200
    assert 'id="action-form"' in page.text
    assert 'id="history-log"' in page.text
    assert 'id="active-objectives"' in page.text
    assert 'id="completed-objectives"' in page.text
    assert 'role="alert"' in page.text
    assert "/sessions/" in script.text
    assert "setBusy" in script.text
    assert "showError" in script.text
    assert "view.active_objectives" in script.text
    assert "view.completed_objectives" in script.text
    assert "02:13" not in page.text + script.text
    assert "fact_blackout_window" not in page.text + script.text


def test_ui_consumed_api_contract_supports_session_action_and_history(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post("/sessions", json={"name": "Browser test"})
    session_id = created.json()["session"]["id"]

    action = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "take brass key"},
    )
    history = client.get(f"/sessions/{session_id}/history?limit=100")

    assert created.status_code == 201
    assert action.status_code == 200
    assert action.json()["accepted"] is True
    assert action.json()["state"]["inventory"][0]["name"] == "brass key"
    assert history.status_code == 200
    assert history.json()["turns"][-1]["raw_input"] == "take brass key"


def test_ui_api_contract_preserves_rejected_action_state(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    created = client.post("/sessions", json={"name": "Reject test"})
    session_id = created.json()["session"]["id"]
    before = created.json()["state"]

    rejected = client.post(
        f"/sessions/{session_id}/actions",
        json={"text": "move nowhere"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["accepted"] is False
    assert rejected.json()["reason"]
    assert rejected.json()["state"] == before
