"""FastAPI app for PhishLens.

POST /analyze takes raw email text and returns the phishing score, the
reasons behind it, and the facts the parser pulled out of the message.
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

try:  # works both as "backend.app" and as "python backend/app.py"
    from .parser import parse_email
    from .rules import evaluate
except ImportError:  # pragma: no cover - script-style execution
    from parser import parse_email
    from rules import evaluate

app = FastAPI(
    title="PhishLens",
    description="Paste an email, get a phishing score with plain-English reasons.",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    raw_email: str = Field(
        ...,
        min_length=1,
        description="The full raw email text, headers and body.",
        examples=["From: a@b.example\nSubject: hi\n\nHello"],
    )


class LinkOut(BaseModel):
    text: str
    url: str


class AnalyzeResponse(BaseModel):
    score: int = Field(..., ge=0, le=100)
    reasons: list[str]
    sender: str | None
    sender_domain: str | None
    reply_to: str | None
    links: list[LinkOut]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    parsed = parse_email(request.raw_email)
    result = evaluate(parsed)

    return AnalyzeResponse(
        score=result.score,
        reasons=result.reasons,
        sender=parsed.sender,
        sender_domain=parsed.sender_domain,
        reply_to=parsed.reply_to,
        links=[LinkOut(text=link.text, url=link.url) for link in parsed.links],
    )
