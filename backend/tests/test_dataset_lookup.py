import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.cqrs import (
    DomainError,
    find_runs_by_dataset_sha,
    normalize_dataset_sha_query,
    start_run,
)
from app.database import Base, get_db
from app.main import app


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


FP_A = sha("casp14-subset-v1")  # 两条 Run 复用，验证一对多
FP_B = sha("kinase-panel-2024q3")


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # JSONB not available on SQLite — remap via create_all with JSON
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(_type, compiler, **kw):
        return "JSON"

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded_db(db):
    start_run(
        db,
        actor="researcher",
        project="protein-folding",
        name="AlphaFold baseline v1",
        dataset_content_sha256=FP_A,
        code_commit_sha="a1b2c3d4e5f6789012345678abcdef0123456789",
        description=None,
    )
    start_run(
        db,
        actor="researcher",
        project="protein-folding",
        name="AlphaFold baseline v2 (recalibrated)",
        dataset_content_sha256=FP_A,
        code_commit_sha="b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5",
        description=None,
    )
    start_run(
        db,
        actor="researcher",
        project="drug-screen",
        name="Kinase panel screen #42",
        dataset_content_sha256=FP_B,
        code_commit_sha="f0e1d2c3b4a5968778695a4b3c2d1e0f98765432",
        description=None,
    )
    return db


def test_exact_match_returns_all_runs_sharing_fingerprint(seeded_db):
    hits = find_runs_by_dataset_sha(seeded_db, FP_A)
    assert len(hits) == 2
    assert {h.name for h in hits} == {
        "AlphaFold baseline v1",
        "AlphaFold baseline v2 (recalibrated)",
    }
    for hit in hits:
        assert hit.dataset_content_sha256 == FP_A
        assert hit.project == "protein-folding"
        assert hit.status == "running"
        assert hit.code_commit_sha
        assert hit.started_at is not None
    # 按启动时间倒序
    started = [h.started_at for h in hits]
    assert started == sorted(started, reverse=True)


def test_prefix_match(seeded_db):
    hits = find_runs_by_dataset_sha(seeded_db, FP_A[:8])
    assert len(hits) == 2
    hits_b = find_runs_by_dataset_sha(seeded_db, FP_B[:12])
    assert len(hits_b) == 1
    assert hits_b[0].name == "Kinase panel screen #42"


def test_query_is_case_and_whitespace_insensitive(seeded_db):
    hits = find_runs_by_dataset_sha(seeded_db, f"  {FP_A.upper()}  ")
    assert len(hits) == 2


def test_no_match_returns_empty(seeded_db):
    assert find_runs_by_dataset_sha(seeded_db, "0" * 64) == []


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "abc123",  # 前缀太短
        "xyz12345",  # 非十六进制
        "g" * 64,
        "a" * 65,  # 超长
    ],
)
def test_invalid_query_rejected(db, raw):
    with pytest.raises(DomainError):
        normalize_dataset_sha_query(raw)


def test_boundary_prefix_lengths_ok(db):
    assert normalize_dataset_sha_query("a" * 8) == "a" * 8
    assert normalize_dataset_sha_query("F" * 64) == "f" * 64


# --- API 级：双角色可查、未登录拒绝、非法输入 400 ---


@pytest.fixture()
def client(seeded_db):
    def _override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _auth(role: str) -> dict:
    username = "researcher" if role == "researcher" else "auditor"
    return {"Authorization": f"Bearer {create_access_token(username, role)}"}


@pytest.mark.parametrize("role", ["researcher", "auditor"])
def test_lookup_endpoint_allows_both_roles(client, role):
    resp = client.get("/api/datasets/lookup", params={"sha": FP_A}, headers=_auth(role))
    assert resp.status_code == 200
    hits = resp.json()
    assert len(hits) == 2
    for hit in hits:
        for key in (
            "run_id",
            "project",
            "name",
            "status",
            "code_commit_sha",
            "dataset_content_sha256",
            "started_at",
            "started_by",
        ):
            assert key in hit


def test_lookup_endpoint_prefix(client):
    resp = client.get("/api/datasets/lookup", params={"sha": FP_B[:8]}, headers=_auth("auditor"))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_lookup_endpoint_requires_login(client):
    resp = client.get("/api/datasets/lookup", params={"sha": FP_A})
    assert resp.status_code == 401


def test_lookup_endpoint_rejects_bad_input(client):
    resp = client.get("/api/datasets/lookup", params={"sha": "abc"}, headers=_auth("researcher"))
    assert resp.status_code == 400
