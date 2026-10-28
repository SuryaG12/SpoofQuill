"""FastAPI app for SpoofQuill.

POST /analyze takes raw email text and returns the phishing score, the
reasons behind it, and the facts the parser pulled out of the message.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

try:  # works both as "backend.app" and as "python backend/app.py"
    from .parser import parse_email
    from .rules import evaluate
except ImportError:  # pragma: no cover - script-style execution
    from parser import parse_email
    from rules import evaluate

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
