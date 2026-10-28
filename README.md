# SpoofQuill

SpoofQuill reads a raw email and scores how much it looks like phishing.

## What it does

Paste an email, headers included, or load one of the examples. SpoofQuill returns a score from 0 to 100, the reasons behind that score, and the sender facts it could pull from the message.

Four signals add points:

- The reply-to address does not match the sender.
- Link text hides where the link goes.
- The message uses urgent language.
- A link asks for payment or a login.

When several signals appear in one message, a stacking bonus adds more points. Unrelated signs together are stronger evidence than any one alone.

## Project structure

- `backend/` holds the FastAPI server, the email parser, and the scoring rules.
- `frontend/` holds the page: paste box, examples, score, and findings.
- `examples/` holds made-up phishing emails for testing.

## Run it

```bash
pip install -r requirements-local.txt
uvicorn backend.app:app --reload
```

Open http://127.0.0.1:8000/ in a browser.

## Run on Cloudflare Workers

This branch runs the same FastAPI app on Cloudflare Python Workers. The page and examples are served from Workers Static Assets, and `/analyze` and `/health` run through FastAPI.

```bash
uv sync
uv run pywrangler dev
```

Open http://127.0.0.1:8787/ in a browser.

`pywrangler deploy` publishes the Worker. No Cloudflare account is needed for local development.

## API

`POST /analyze` takes JSON with a `raw_email` field and returns the score, the reasons, the sender, the sender domain, the reply-to address, and the links.
