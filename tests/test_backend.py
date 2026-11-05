"""Tests for parsing, scoring, validation, and the shipped static files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app import AnalyzeRequest, AnalyzeResponse, analyze
from backend.parser import parse_email, parse_fields
from backend.rules import evaluate

ROOT = Path(__file__).resolve().parent.parent

ALL_FOUR = {
    "sender": "support@paypa1-secure.example",
    "reply_to": "help@account-review.example",
    "subject": "Urgent: your account is suspended",
    "body": (
        "<p>Act now: "
        '<a href="http://login-verify.example/session">'
        "https://www.paypal.com/signin</a></p>"
    ),
}

VALID = {
    "sender": "user@example.com",
    "reply_to": "",
    "subject": "Account notice",
    "body": "This message is long enough to pass the body check.",
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def example_fields(number: int) -> dict[str, str]:
    """Read an example the same way the page fills the four fields."""
    text = read(f"examples/example{number}.txt").replace("\r\n", "\n")
    headers, _, body = text.partition("\n\n")
    fields = {"sender": "", "reply_to": "", "subject": "", "body": body.strip()}

    for line in headers.splitlines():
        match = re.match(r"^(From|Reply-To|Subject):\s*(.*)$", line, re.IGNORECASE)
        if not match:
            continue
        key = match.group(1).lower()
        raw = match.group(2).strip()
        if key == "subject":
            fields["subject"] = raw
            continue
        angle = re.search(r"<([^<>]+)>", raw)
        address = angle.group(1) if angle else re.search(r"[^\s<>]+@[^\s<>]+", raw).group(0)
        fields["sender" if key == "from" else "reply_to"] = address

    return fields


def call(payload: dict) -> AnalyzeResponse:
    return analyze(AnalyzeRequest(**payload))


@pytest.mark.parametrize("number, expected", [(1, 50), (2, 38), (3, 44)])
def test_examples_score_from_raw_email(number: int, expected: int) -> None:
    assert evaluate(parse_email(read(f"examples/example{number}.txt"))).score == expected


@pytest.mark.parametrize("number, expected", [(1, 50), (2, 38), (3, 44)])
def test_examples_score_from_fields(number: int, expected: int) -> None:
    assert evaluate(parse_fields(**example_fields(number))).score == expected


def test_all_four_signals_score_100() -> None:
    parsed = parse_fields(**ALL_FOUR)
    result = evaluate(parsed)

    assert result.score == 100
    assert [(link.text, link.url) for link in parsed.links] == [
        ("https://www.paypal.com/signin", "http://login-verify.example/session")
    ]


def test_plain_urls_are_extracted_from_the_body() -> None:
    parsed = parse_fields(
        "sender@example.com",
        "",
        "Delivery notice",
        "Check the status at http://delivery.example/status today.",
    )

    assert [(link.text, link.url) for link in parsed.links] == [
        ("http://delivery.example/status", "http://delivery.example/status")
    ]


def test_reply_to_matching_sender_is_dropped() -> None:
    parsed = parse_fields("Sender@Example.com", "sender@example.com", "Hello", "A" * 20)
    assert parsed.reply_to is None


def test_structured_request_scores_like_the_parser() -> None:
    response = call(ALL_FOUR)

    assert response.score == 100
    assert response.sender == ALL_FOUR["sender"]
    assert response.reply_to == ALL_FOUR["reply_to"]
    assert len(response.links) == 1


def test_raw_email_still_works() -> None:
    assert call({"raw_email": read("examples/example1.txt")}).score == 50


def test_raw_email_takes_precedence_over_structured_fields() -> None:
    response = call(
        {
            "raw_email": read("examples/example1.txt"),
            "sender": "not-an-email",
            "subject": "",
            "body": "",
        }
    )
    assert response.score == 50


def test_unknown_domains_are_allowed() -> None:
    response = call({**VALID, "sender": "user@gnail.com"})
    assert response.sender_domain == "gnail.com"


@pytest.mark.parametrize(
    "payload, detail",
    [
        ({"sender": "", "subject": "Hello", "body": "A" * 25}, "From is required."),
        (
            {"sender": "user@gnail", "subject": "Hello", "body": "A" * 25},
            "From must be a valid email address.",
        ),
        (
            {
                "sender": "a@b.example",
                "reply_to": "nope",
                "subject": "Hello",
                "body": "A" * 25,
            },
            "Reply-To must be a valid email address.",
        ),
        (
            {"sender": "a@b.example", "subject": "Hi", "body": "A" * 25},
            "Subject must be at least 3 characters.",
        ),
        (
            {"sender": "a@b.example", "subject": "Hello", "body": "too short"},
            "Message must be at least 20 characters.",
        ),
    ],
)
def test_structured_validation(payload: dict, detail: str) -> None:
    with pytest.raises(HTTPException) as error:
        call(payload)

    assert error.value.status_code == 422
    assert error.value.detail == detail


def test_empty_request_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        call({})

    assert error.value.status_code == 422


def normalized(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_frontend_and_public_copies_match() -> None:
    assert normalized(ROOT / "frontend/index.html") == normalized(ROOT / "public/index.html")

    for number in (1, 2, 3):
        source = ROOT / f"examples/example{number}.txt"
        copy = ROOT / f"public/examples/example{number}.txt"
        assert normalized(source) == normalized(copy)


@pytest.mark.parametrize("path", ["frontend/index.html", "public/index.html"])
def test_pages_have_no_em_dashes(path: str) -> None:
    assert "\u2014" not in read(path)
