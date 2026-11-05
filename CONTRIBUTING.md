# Contributing to SpoofQuill

Thanks for taking the time to improve SpoofQuill.

## Before you start

- Search the existing issues and pull requests so work is not duplicated.
- For a large change, open an issue first to agree on the approach.
- Never commit real email addresses, credentials, or `.env` / `.dev.vars` files. Use the made-up addresses in `examples/`.

## Local setup

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

To run the app locally:

```bash
pip install -r requirements-local.txt
uvicorn backend.app:app --reload
```

To run the Cloudflare Workers build:

```bash
uv sync
uv run pywrangler dev
```

## Making a change

1. Fork the repository and branch from `main`.
2. Keep changes focused. One fix or feature per pull request.
3. Match the existing style. The project uses plain Python, FastAPI, and a single static HTML page.
4. Add or update tests in `tests/` when behavior changes.
5. Run `python -m pytest -q` before opening the pull request.
6. If you edit `frontend/index.html`, copy the same file to `public/index.html`. A test fails when the two copies differ.

## Pull requests

- Describe what changed and why.
- Link the related issue when one exists.
- State how you tested the change.
- Keep the pull request small enough to review.

## Reporting bugs

Open an issue with the steps to reproduce, the expected result, and the actual result. Include the Python version and the command you ran. Do not paste real private email content. Use the examples or a made-up message.

## Security issues

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).
