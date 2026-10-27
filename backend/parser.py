"""Email parsing for PhishLens.

Turns raw email text into the few facts the scoring rules will need:

* who sent it, and the domain that address belongs to
* a reply-to address, but only when it actually differs from the sender
* every link, keeping the text the reader sees next to the URL it really
  points at (that mismatch is the interesting part for phishing)

This module only extracts. It makes no judgement about whether anything is
suspicious - that belongs in rules.py.

Works with a full raw email (headers plus body) and with a bare pasted body.
Text and HTML bodies are both handled; non-http links (mailto:, tel:, "#")
are ignored.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from email import message_from_string, policy
from email.message import Message
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlsplit

ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
TRAILING_PUNCT = ".,;:!?)"
FROM_LINE_RE = re.compile(r"^\s*(from|reply-to)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
EMAIL_RE = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[A-Za-z]{2,}")


@dataclass
class Link:
    """A link as it appears in the email: what the reader sees vs. where it goes."""

    text: str
    url: str


@dataclass
class ParsedEmail:
    sender: str | None = None
    sender_domain: str | None = None
    reply_to: str | None = None
    links: list[Link] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "sender_domain": self.sender_domain,
            "reply_to": self.reply_to,
            "links": [{"text": link.text, "url": link.url} for link in self.links],
        }


def parse_email(raw: str) -> ParsedEmail:
    """Parse raw email text into sender, domain, reply-to and links."""
    message = message_from_string(raw, policy=policy.default)
    body_text = _body_text(message)

    sender = _address(message.get("From")) or _address_from_body(body_text, "from")
    reply_to = _address(message.get("Reply-To")) or _address_from_body(body_text, "reply-to")

    # A reply-to pointing at the sender adds nothing; keep only real differences.
    if reply_to and sender and reply_to.lower() == sender.lower():
        reply_to = None

    return ParsedEmail(
        sender=sender,
        sender_domain=_domain(sender),
        reply_to=reply_to,
        links=_extract_links(body_text),
    )


def _address(value) -> str | None:
    """Pull the bare address out of a header value like 'Name <a@b.com>'."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    _, address = parseaddr(text)
    if address and "@" in address:
        return address
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def _address_from_body(body: str, header: str) -> str | None:
    """Fall back to a 'From:' / 'Reply-To:' line in pasted text."""
    for match in FROM_LINE_RE.finditer(body):
        if match.group(1).lower() == header:
            return _address(match.group(2))
    return None


def _domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[1].strip().lower() or None


def _body_text(message: Message) -> str:
    """Concatenate the readable body, whether the email is plain text or HTML."""
    chunks: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_type() in ("text/plain", "text/html"):
                chunks.append(_part_text(part))
    else:
        chunks.append(_part_text(message))

    return "\n".join(chunk for chunk in chunks if chunk)


def _part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        payload = part.get_payload()
        return payload if isinstance(payload, str) else ""

    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _extract_links(body: str) -> list[Link]:
    """Collect anchor links and bare URLs, de-duplicated, in order of appearance."""
    links: list[Link] = []
    seen: set[tuple[str, str]] = set()

    def add(text: str, url: str) -> None:
        url = html.unescape(url).strip()
        if not url.lower().startswith(("http://", "https://")):
            return
        text = " ".join(text.split()) or url
        key = (text, url)
        if key not in seen:
            seen.add(key)
            links.append(Link(text=text, url=url))

    # 1. Anchors: text the reader sees, href where it actually goes.
    masked = body
    for match in ANCHOR_RE.finditer(body):
        attributes, anchor_text = match.group(1), match.group(2)
        href = HREF_RE.search(attributes)
        if href:
            url = next((group for group in href.groups() if group), "")
            visible = html.unescape(TAG_RE.sub(" ", anchor_text))
            add(visible, url)
        # Blank out the anchor so step 2 does not report it a second time.
        masked = masked[: match.start()] + " " * (match.end() - match.start()) + masked[match.end() :]

    # 2. Bare URLs left in the remaining text (plain-text emails mostly).
    for match in URL_RE.finditer(html.unescape(TAG_RE.sub(" ", masked))):
        url = match.group(0).rstrip(TRAILING_PUNCT)
        add(url, url)

    return links


def _demo() -> None:
    import json

    root = Path(__file__).resolve().parent.parent
    example = root / "examples" / "example1.txt"
    print(f"--- {example} ---")
    print(json.dumps(parse_email(example.read_text(encoding="utf-8")).to_dict(), indent=2))

    # The examples are body-only, so show header handling with a small sample.
    print("\n--- sample with headers and an HTML body ---")
    sample = (
        'From: "Billing Dept" <billing@accounts-fake-bank.example>\n'
        "Reply-To: recover@lookalike-bank.example\n"
        "Subject: Verify now\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        '<p>Please <a href="http://fake-login-example.com/verify">log in to your real bank</a>.</p>'
    )
    print(json.dumps(parse_email(sample).to_dict(), indent=2))


if __name__ == "__main__":
    _demo()
