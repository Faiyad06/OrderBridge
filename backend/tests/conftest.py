import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.agent import orchestrator
from app.seed import seed

ORIGIN = "http://localhost:8000"


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db.reset_thread_connections()
    seed(path)
    db.clock._offset_seconds = 0
    orchestrator.set_client_factory(None)
    yield path
    db.reset_thread_connections()
    orchestrator.set_client_factory(None)


class Api:
    def __init__(self, username, password="orderbridge-demo"):
        from app.main import app
        self.c = TestClient(app, headers={"Origin": ORIGIN})
        r = self.c.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, headers=None, **kw):
        return self.c.post(url, json=json, headers={"X-CSRF-Token": self.csrf, **(headers or {})}, **kw)

    def patch(self, url, json=None):
        return self.c.patch(url, json=json, headers={"X-CSRF-Token": self.csrf})


@pytest.fixture()
def owner(db_path):
    return Api("owner@demo-gba")


@pytest.fixture()
def viewer(db_path):
    return Api("viewer@demo-gba")


@pytest.fixture()
def other_owner(db_path):
    return Api("owner@demo-other")


def accept_combined_and_init(api):
    assert api.post("/api/workspace/load-example").status_code == 200
    for cid in ("buyer_deposit_30pct", "supplier_deferral_50pct"):
        assert api.post("/api/scenarios/combined_terms/conditions", json={"condition_id": cid, "accept": True}).status_code == 200
    r = api.post("/api/sandbox/initialize")
    assert r.status_code == 200, r.text
    return r.json()


def prepare(api, amount="70000.00", key="k1", recipient="SUP-MAT-001", obligation="ORD-001-MAT-1"):
    return api.post("/api/actions/prepare", json={"scenario_id": "combined_terms", "obligation_event_id": obligation, "recipient_id": recipient,
                                                  "amount": amount, "idempotency_key": key})
