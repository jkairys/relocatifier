"""API tests via TestClient with the fetch/run layer faked (no network)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scraper import runs as runs_module
from scraper.api import create_app
from scraper.config import load_settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path):
    base = load_settings()
    return replace(
        base,
        duckdb_path=tmp_path / "listings.duckdb",
        metrics_path=FIXTURES / "metrics.json",
        sitemap_cache_path=FIXTURES / "oth_sitemap.xml",
        sales_artifact_path=tmp_path / "sales.json",
    )


@pytest.fixture
def client(settings, monkeypatch):
    # Neutralise the background run: record that it was scheduled, do no network.
    scheduled: list[tuple] = []

    def fake_execute_run(db_path, s, registry, run_id, sal_codes, **kwargs):
        scheduled.append((run_id, sal_codes))
        registry.finish(run_id, "completed", {"suburbs": {}, "errors": []})

    monkeypatch.setattr(runs_module, "execute_run", fake_execute_run)
    # api.py imported execute_run by name, so patch there too.
    import scraper.api as api_module

    monkeypatch.setattr(api_module, "execute_run", fake_execute_run)

    app = create_app(settings)
    tc = TestClient(app)
    tc.scheduled = scheduled  # type: ignore[attr-defined]
    return tc


class TestHealth:
    def test_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestWatchlist:
    def test_empty_initially(self, client):
        assert client.get("/watchlist").json() == []

    def test_add_resolves_slug(self, client):
        res = client.post("/watchlist/30900")  # Bli Bli QLD
        assert res.status_code == 201
        body = res.json()
        assert body["oth_slug"] == "bli-bli-4560"
        assert body["listing_count"] == 0

    def test_add_then_listed(self, client):
        client.post("/watchlist/30900")
        listed = client.get("/watchlist").json()
        assert len(listed) == 1
        assert listed[0]["sal_code"] == "30900"

    def test_add_duplicate_409(self, client):
        client.post("/watchlist/30900")
        res = client.post("/watchlist/30900")
        assert res.status_code == 409

    def test_unknown_sal_404(self, client):
        res = client.post("/watchlist/99999")
        assert res.status_code == 404

    def test_ambiguous_slug_422_with_detail(self, client):
        res = client.post("/watchlist/39999")  # Newtown QLD — ambiguous
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "newtown-4305" in detail
        assert "issue #2" in detail

    def test_unresolvable_slug_422(self, client):
        res = client.post("/watchlist/49999")  # Nowhereville — no slug
        assert res.status_code == 422

    def test_delete_204_keeps_nothing_required(self, client):
        client.post("/watchlist/30900")
        res = client.delete("/watchlist/30900")
        assert res.status_code == 204
        assert client.get("/watchlist").json() == []


class TestRuns:
    def test_start_run_202(self, client):
        client.post("/watchlist/30900")
        res = client.post("/runs", json={})
        assert res.status_code == 202
        assert "run_id" in res.json()
        # background task ran (faked) and was recorded
        assert len(client.scheduled) == 1

    def test_run_status_fetchable(self, client):
        client.post("/watchlist/30900")
        run_id = client.post("/runs", json={}).json()["run_id"]
        res = client.get(f"/runs/{run_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "completed"

    def test_run_with_sal_codes(self, client):
        client.post("/watchlist/30900")
        res = client.post("/runs", json={"sal_codes": ["30900"]})
        assert res.status_code == 202
        assert client.scheduled[0][1] == ["30900"]

    def test_unknown_run_404(self, client):
        assert client.get("/runs/deadbeef").status_code == 404

    def test_recent_runs_newest_first(self, client):
        client.post("/watchlist/30900")
        client.post("/runs", json={})
        client.post("/runs", json={})
        runs_list = client.get("/runs?limit=10").json()
        assert len(runs_list) == 2


class TestExport:
    def test_export_writes_artifact(self, client, settings):
        client.post("/watchlist/30900")
        res = client.post("/export")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["path"] == str(settings.sales_artifact_path)

        import json

        data = json.loads(settings.sales_artifact_path.read_text())
        assert data["schema_version"] == 2
        assert "30900" in data["suburbs"]
