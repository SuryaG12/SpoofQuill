# SpoofScope

SpoofScope reads a raw email and scores how much it looks like phishing.

## What it does

Paste an email, headers included, or load one of the examples. SpoofScope returns a score from 0 to 100, the reasons behind that score, and the sender facts it could pull from the message.

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
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Open http://127.0.0.1:8000/ in a browser.

## API

`POST /analyze` takes JSON with a `raw_email` field and returns the score, the reasons, the sender, the sender domain, the reply-to address, and the links.
