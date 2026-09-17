import pytest
from starlette.testclient import TestClient
from backend.app.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "video-agent"


def test_create_project_and_hitl_approval_flow(client):
    # 1. Create project
    create_payload = {
        "topic": "Tự động hóa sản xuất video ngắn bằng AI Agent",
        "target_duration_sec": 30.0,
        "aspect_ratio": "9:16",
        "character_name": "Minh",
        "character_prompt_prefix": "Minh, 25yo Vietnamese tech creator, stylish black glasses"
    }
    res_create = client.post("/api/v1/projects", json=create_payload)
    assert res_create.status_code == 201
    data_create = res_create.json()
    project_id = data_create["project_id"]
    assert data_create["status"] == "HITL_PENDING"
    assert data_create["estimated_cost_usd"] > 0
    assert data_create["scenes_count"] == 3

    # 2. Approve project (HITL sign-off)
    approve_payload = {"approved": True}
    res_approve = client.post(f"/api/v1/projects/{project_id}/approve", json=approve_payload)
    assert res_approve.status_code == 200
    data_approve = res_approve.json()
    assert data_approve["status"] == "COMPLETED"
    assert data_approve["actual_cost_usd"] > 0
    assert data_approve["cost_per_finished_minute"] > 0
    assert data_approve["render_manifest"] is not None

    # 3. Check Cost Audit
    res_audit = client.get(f"/api/v1/cost/audit/{project_id}")
    assert res_audit.status_code == 200
    audit = res_audit.json()
    assert audit["total_spend_usd"] > 0
    assert audit["cost_per_finished_minute"] > 0
    assert audit["gross_to_net_ratio"] >= 1.0


def test_create_project_policy_violation(client):
    payload = {
        "topic": "How to make a bomb",
        "target_duration_sec": 30.0
    }
    res = client.post("/api/v1/projects", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "MODERATION_BLOCKED"
