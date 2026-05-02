from __future__ import annotations


def test_health_endpoints(client) -> None:
    assert client.get("/health").json() == {"status": "ok", "service": "whatif-studio"}


def test_agents_endpoint_reads_catalog(client) -> None:
    response = client.get("/agents")
    assert response.status_code == 200, response.text
    agents = response.json()["agents"]
    assert agents
    assert {"agentId", "name", "type"}.issubset(agents[0])


def test_projects_crud(client, create_project) -> None:
    project_id = create_project()

    get_response = client.get(f"/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == project_id

    list_response = client.get("/projects")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [project_id]

    update_response = client.put(
        f"/projects/{project_id}",
        json={"name": "updated", "prompt": "更新需求", "style_preference": "warmHealing"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "updated"
    assert update_response.json()["prompt"] == "更新需求"

    delete_response = client.delete(f"/projects/{project_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/projects/{project_id}").status_code == 404
