import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import get_db
from app.cqrs import start_run
from app.database import Base
from app.main import app


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture()
def client():
    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(_type, compiler, **kw):
        return "JSON"

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    fp1 = sha("casp14-subset-v1")
    fp2 = sha("kinase-panel-2024q3")
    start_run(
        db,
        actor="researcher",
        project="protein-folding",
        name="AlphaFold baseline v1",
        dataset_content_sha256=fp1,
        code_commit_sha="a1b2c3d4e5f6789012345678abcdef0123456789",
        description=None,
        run_id=uuid4(),
    )
    start_run(
        db,
        actor="researcher",
        project="drug-screen",
        name="Kinase panel screen #42",
        dataset_content_sha256=fp2,
        code_commit_sha="f0e1d2c3b4a5968778695a4b3c2d1e0f98765432",
        description=None,
        run_id=uuid4(),
    )

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)  # plain construction skips lifespan (no PG create_all)
    yield c, fp1, fp2
    app.dependency_overrides.clear()
    db.close()


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_lookup_requires_auth(client):
    c, fp1, _ = client
    r = c.get("/api/dataset-fingerprints/lookup", params={"fingerprint": fp1})
    assert r.status_code == 401


@pytest.mark.parametrize("role", ["researcher", "auditor"])
def test_lookup_exact_for_both_roles(client, role):
    c, fp1, _ = client
    password = "lab123456" if role == "researcher" else "audit123456"
    headers = _login(c, role, password)

    # uppercase fingerprint is normalized to lowercase
    r = c.get(
        "/api/dataset-fingerprints/lookup",
        params={"fingerprint": fp1.upper()},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    row = data[0]
    assert row["name"] == "AlphaFold baseline v1"
    for field in ("project", "name", "status", "code_commit_sha", "started_at", "id"):
        assert field in row


def test_lookup_prefix(client):
    c, _, fp2 = client
    headers = _login(c, "auditor", "audit123456")
    r = c.get(
        "/api/dataset-fingerprints/lookup",
        params={"fingerprint": fp2[:12]},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "Kinase panel screen #42"


def test_lookup_no_hit(client):
    c, _, _ = client
    headers = _login(c, "auditor", "audit123456")
    r = c.get(
        "/api/dataset-fingerprints/lookup",
        params={"fingerprint": "0" * 64},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == []


def test_lookup_rejects_non_hex_and_short(client):
    c, _, _ = client
    headers = _login(c, "auditor", "audit123456")
    bad_hex = c.get(
        "/api/dataset-fingerprints/lookup",
        params={"fingerprint": "z" * 12},
        headers=headers,
    )
    assert bad_hex.status_code == 422
    too_short = c.get(
        "/api/dataset-fingerprints/lookup",
        params={"fingerprint": "abc123"},
        headers=headers,
    )
    assert too_short.status_code == 422


def test_lookup_result_can_open_detail_and_lineage(client):
    c, fp1, _ = client
    headers = _login(c, "researcher", "lab123456")
    found = c.get(
        "/api/dataset-fingerprints/lookup",
        params={"fingerprint": fp1},
        headers=headers,
    ).json()
    run_id = found[0]["id"]
    assert c.get(f"/api/runs/{run_id}", headers=headers).status_code == 200
    assert c.get(f"/api/runs/{run_id}/lineage", headers=headers).status_code == 200
