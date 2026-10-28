"""FastAPI app for SpoofQuill.

POST /analyze takes either raw email text or the separate sender, reply_to,
subject and body fields. It returns the phishing score, the reasons behind
it, and the facts the parser pulled out of the message.
"""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

try:  # works both as "backend.app" and as "python backend/app.py"
    from .parser import parse_email, parse_fields
    from .rules import evaluate
except ImportError:  # pragma: no cover - script-style execution
    from parser import parse_email, parse_fields
    from rules import evaluate

EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")

SUBJECT_MIN = 3
BODY_MIN = 20

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(
    title="SpoofQuill",
    description="Paste an email and get a phishing score with the reasons behind it.",
    version="0.1.0",
)

# The page may be opened from disk or another local port during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    """Either a full raw email or the same facts as separate fields.

    ``raw_email`` keeps the original API working. When it is absent the
    structured fields are validated and parsed directly.
    """

    raw_email: str | None = Field(
        default=None,
        description="The full raw email text, headers and body.",
        examples=["From: a@b.example\nSubject: hi\n\nHello"],
    )
    sender: str | None = Field(default=None, description="The From address.")
    reply_to: str | None = Field(default=None, description="Optional Reply-To address.")
    subject: str | None = Field(default=None, description="The Subject line.")
    body: str | None = Field(default=None, description="The message body, plain text or HTML.")


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


def _structured_input(request: AnalyzeRequest):
    """Validate the separate fields and build the same object the parser would."""
    sender = (request.sender or "").strip()
    reply_to = (request.reply_to or "").strip()
    subject = (request.subject or "").strip()
    body = request.body or ""

    if not sender:
        raise HTTPException(status_code=422, detail="From is required.")
    if not EMAIL_RE.fullmatch(sender):
        raise HTTPException(status_code=422, detail="From must be a valid email address.")
    if reply_to and not EMAIL_RE.fullmatch(reply_to):
        raise HTTPException(status_code=422, detail="Reply-To must be a valid email address.")
    if len(subject) < SUBJECT_MIN:
        raise HTTPException(status_code=422, detail="Subject must be at least 3 characters.")
    if len(body.strip()) < BODY_MIN:
        raise HTTPException(status_code=422, detail="Message must be at least 20 characters.")

    return parse_fields(sender, reply_to or None, subject, body)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    raw_email = (request.raw_email or "").strip()
    if raw_email:
        parsed = parse_email(raw_email)
    elif request.sender is not None or request.subject is not None or request.body is not None:
        parsed = _structured_input(request)
    else:
        raise HTTPException(
            status_code=422,
            detail="Send raw_email or the separate sender, reply_to, subject and body fields.",
        )

    result = evaluate(parsed)

    return AnalyzeResponse(
        score=result.score,
        reasons=result.reasons,
        sender=parsed.sender,
        sender_domain=parsed.sender_domain,
        reply_to=parsed.reply_to,
        links=[LinkOut(text=link.text, url=link.url) for link in parsed.links],
    )


async def _static_file(asset_path: str, local_path: str, request: Request) -> Response:
    """Serve a local file, or the same path from Cloudflare's ASSETS binding."""
    env = request.scope.get("env")
    assets = getattr(env, "ASSETS", None) if env is not None else None
    if assets is not None:
        asset = await assets.fetch(f"https://assets.local/{asset_path}")
        return Response(
            content=await asset.bytes(),
            status_code=asset.status,
            headers=asset.headers,
        )

    path = PROJECT_ROOT / local_path
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


@app.get("/", include_in_schema=False)
async def frontend(request: Request) -> Response:
    """Serve the page locally and through the Worker's static assets."""
    return await _static_file("index.html", "frontend/index.html", request)


@app.get("/examples/{filename}", include_in_schema=False)
async def example(filename: str, request: Request) -> Response:
    """Serve the sample emails locally and through the Worker's static assets."""
    if filename != Path(filename).name or not filename.endswith(".txt"):
        raise HTTPException(status_code=404)
    path = f"examples/{filename}"
    return await _static_file(path, path, request)
