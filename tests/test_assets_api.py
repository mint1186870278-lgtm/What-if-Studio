from __future__ import annotations


def test_assets_upload_list_download_and_delete(client, create_project) -> None:
    project_id = create_project()

    upload_response = client.post(
        f"/{project_id}/assets",
        files={"file": ("clip.mp4", b"video-bytes", "video/mp4")},
        data={"asset_type": "video"},
    )
    assert upload_response.status_code == 201, upload_response.text
    asset = upload_response.json()

    list_response = client.get(f"/{project_id}/assets")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [asset["id"]]

    download_response = client.get(f"/{project_id}/assets/{asset['id']}/download")
    assert download_response.status_code == 200
    assert download_response.content == b"video-bytes"

    delete_response = client.delete(f"/{project_id}/assets/{asset['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/{project_id}/assets/{asset['id']}").status_code == 404
