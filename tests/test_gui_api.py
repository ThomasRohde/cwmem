from __future__ import annotations

from pathlib import Path

import pytest

from cwmem.core.store import ensure_schema


@pytest.fixture
def initialized_root(tmp_path: Path) -> Path:
    """Create an initialized cwmem repo in tmp_path."""
    # Create required directories
    (tmp_path / ".cwmem").mkdir()
    (tmp_path / ".cwmem" / "logs").mkdir()
    (tmp_path / ".cwmem" / "plans").mkdir()
    (tmp_path / "memory" / "entries").mkdir(parents=True)
    (tmp_path / "memory" / "events").mkdir(parents=True)
    (tmp_path / "memory" / "graph").mkdir(parents=True)
    (tmp_path / "memory" / "taxonomy").mkdir(parents=True)
    (tmp_path / "memory" / "manifests").mkdir(parents=True)
    ensure_schema(tmp_path)
    return tmp_path


@pytest.fixture
def client(initialized_root: Path):
    from starlette.testclient import TestClient

    from cwmem.gui.server import create_app

    app = create_app(initialized_root)
    return TestClient(app)


def test_dashboard_returns_stats(client) -> None:
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "stats" in data


def test_entries_returns_list(client) -> None:
    resp = client.get("/api/entries")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_events_returns_list(client) -> None:
    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_search_empty_query_returns_empty(client) -> None:
    resp = client.get("/api/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []


def test_resource_not_found(client) -> None:
    resp = client.get("/api/resources/nonexistent-000099")
    assert resp.status_code == 404


def test_create_entry_dry_run(client) -> None:
    body = {
        "title": "Test entry",
        "body": "Some body content here.",
        "type": "note",
        "status": "active",
        "tags": [],
    }
    resp = client.post("/api/entries?dry_run=true", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("dry_run") is True


def test_create_entry_and_list(client) -> None:
    body = {
        "title": "Integration test entry",
        "body": "Created by test_gui_api.",
        "type": "note",
        "status": "active",
    }
    resp = client.post("/api/entries", json=body)
    assert resp.status_code == 200

    resp2 = client.get("/api/entries")
    entries = resp2.json()
    assert any(e["title"] == "Integration test entry" for e in entries)


def test_create_entry_then_graph(client) -> None:
    body = {
        "title": "Graph test entry",
        "body": "For graph endpoint test.",
    }
    resp = client.post("/api/entries", json=body)
    assert resp.status_code == 200
    result = resp.json()
    entry = result.get("entry", {})
    entry_id = entry.get("public_id")
    if not entry_id:
        pytest.skip("Could not extract entry ID from create response")

    resp2 = client.get(f"/api/graph/{entry_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert "root" in data
    assert data["root"]["resource_id"] == entry_id


def test_graph_overview_empty(client) -> None:
    resp = client.get("/api/graph-overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "root" in data
    assert "nodes" in data
    assert "edges" in data


def test_graph_overview_with_data(client) -> None:
    client.post("/api/entries", json={"title": "A", "body": "First entry."})
    client.post("/api/entries", json={"title": "B", "body": "Second entry."})
    resp = client.get("/api/graph-overview")
    assert resp.status_code == 200
    data = resp.json()
    # root + at least one node
    all_ids = [data["root"]["resource_id"]] + [n["resource_id"] for n in data["nodes"]]
    assert len(all_ids) >= 2


def test_static_index_served(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "cwmem" in resp.text
