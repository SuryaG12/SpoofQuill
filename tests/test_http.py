"""HTTP-level tests for the routes the Worker and local server expose."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)

STRUCTURED = {
    "sender": "support@paypa1-secure.example",
    "reply_to": "help@account-review.example",
    "subject": "Urgent: your account is suspended",
    "body": (
        "<p>Act now: "
        '<a href="http://login-verify.example/session">'
        "https://www.paypal.com/signin</a></p>"
    ),
}


def normalized(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n")


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_serves_the_frontend() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert normalized_text(response.text) == normalized(ROOT / "frontend/index.html")


@pytest.mark.parametrize("number", [1, 2, 3])
def test_examples_are_served(number: int) -> None:
    response = client.get(f"/examples/example{number}.txt")
    assert response.status_code == 200
    assert normalized_text(response.text) == normalized(ROOT / f"examples/example{number}.txt")


def test_missing_example_returns_404() -> None:
    assert client.get("/examples/missing.txt").status_code == 404


def test_non_txt_example_returns_404() -> None:
    assert client.get("/examples/app.py").status_code == 404


def test_analyze_accepts_structured_fields() -> None:
    response = client.post("/analyze", json=STRUCTURED)
    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 100
    assert body["sender"] == STRUCTURED["sender"]
    assert len(body["links"]) == 1


def test_analyze_accepts_raw_email() -> None:
    raw = normalized(ROOT / "examples/example1.txt")
    response = client.post("/analyze", json={"raw_email": raw})
    assert response.status_code == 200
    assert response.json()["score"] == 50


def test_analyze_rejects_a_short_message() -> None:
    response = client.post(
        "/analyze",
        json={
            "sender": "user@example.com",
            "subject": "Account notice",
            "body": "too short",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Message must be at least 20 characters."


def test_analyze_rejects_an_empty_request() -> None:
    assert client.post("/analyze", json={}).status_code == 422


@pytest.mark.parametrize(
    "path, content_type",
    [
        ("/favicon.ico", "image/"),
        ("/favicon.svg", "image/svg+xml"),
        ("/apple-touch-icon.png", "image/png"),
        ("/og.png", "image/png"),
    ],
)
def test_brand_assets_are_served(path: str, content_type: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.content


def test_page_has_link_preview_metadata() -> None:
    html = normalized(ROOT / "frontend/index.html")
    for marker in (
        'rel="canonical"',
        'rel="icon"',
        'rel="apple-touch-icon"',
        'property="og:image"',
        'name="twitter:card"',
    ):
        assert marker in html


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/health",
        "/favicon.ico",
        "/favicon.svg",
        "/apple-touch-icon.png",
        "/og.png",
        "/examples/example1.txt",
    ],
)
def test_head_matches_get_without_a_body(path: str) -> None:
    get_response = client.get(path)
    head_response = client.head(path)

    assert get_response.status_code == 200
    assert head_response.status_code == get_response.status_code
    assert head_response.content == b""
    assert head_response.headers["content-type"] == get_response.headers["content-type"]
    assert head_response.headers["content-length"] == get_response.headers["content-length"]


def test_head_root_keeps_the_preview_tags_on_get() -> None:
    html = client.get("/").text
    for tag in ("og:title", "og:description", "og:image", "og:url"):
        assert f'property="{tag}"' in html
