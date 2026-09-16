from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app


def test_home_page_and_assets_are_served() -> None:
    with TestClient(app) as client:
        home = client.get("/")
        styles = client.get("/static/styles.css")
        script = client.get("/static/app.js")

    assert home.status_code == 200
    assert "Contract Redactor" in home.text
    assert "脱敏完成后，PDF 会显示在这里" in home.text
    assert "合同及权属编号" in home.text
    assert "普通日期、金额和合同条款默认保留" in home.text
    assert styles.status_code == 200
    assert "--green-600" in styles.text
    assert script.status_code == 200
    assert 'fetch("/api/jobs"' in script.text


def test_document_upload_rejects_unsupported_file_type() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            content=b"not a contract",
            headers={"X-Filename": "notes.txt", "Content-Type": "application/octet-stream"},
        )

    assert response.status_code == 415
    assert response.json()["detail"] == "仅支持 PDF、DOC 和 DOCX 文件"
