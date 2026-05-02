from __future__ import annotations


def test_generate_requires_script(client, create_project) -> None:
    project_id = create_project()
    response = client.post(f"/{project_id}/generate")
    assert response.status_code == 409
    assert "script" in response.text
