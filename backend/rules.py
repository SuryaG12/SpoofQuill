"""Phishing scoring rules for Quyllwrit.

Takes a ParsedEmail and turns the signals we can see into a 0-100 score plus
plain-English reasons a person can read.

Four rules so far:

1. the reply-to domain differs from the sender domain
2. the text of a link names a different domain than the link actually uses
3. urgency language ("urgent", "immediately", "suspended", "verify now", ...)
4. a link that asks for a payment or a login

No single rule can produce a high score on its own. The score is the sum of
the rules that fire, plus a bonus once two or more independent rules fire,
because several unrelated warning signs together are much stronger evidence
than any one of them.

The score is built from the subject, body, sender and links that ParsedEmail
already carries, so evaluate() needs nothing but the parsed email.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

try:  # works both as "backend.rules" and as "python backend/rules.py"
    from .parser import ParsedEmail, parse_email
except ImportError:  # pragma: no cover - script-style execution
    from parser import ParsedEmail, parse_email

# Points per rule. A lone weak-ish signal stays well under 40.
REPLY_TO_MISMATCH = 20
LINK_TEXT_MISMATCH = 30
PAYMENT_OR_LOGIN_LINK = 20
URGENCY_BY_TERM_COUNT = {0: 0, 1: 8, 2: 14}  # 3+ terms -> 20

# Extra points once independent rules stack up.
STACK_BONUS = {0: 0, 1: 0, 2: 10, 3: 20, 4: 25}

URGENCY_PATTERNS = [
    (re.compile(r"\burgent(?:ly)?\b", re.I), "urgent"),
    (re.compile(r"\bimmediately\b", re.I), "immediately"),
    (re.compile(r"\bsuspended?\b", re.I), "suspended"),
    (re.compile(r"\bverify now\b", re.I), "verify now"),
    (re.compile(r"\bact now\b", re.I), "act now"),
    (re.compile(r"\baction required\b", re.I), "action required"),
    (re.compile(r"\bfinal (?:notice|warning)\b", re.I), "final notice"),
    (re.compile(r"\b(?:24|48|72)\s*hours?\b", re.I), "a deadline in hours"),
]

LOGIN_HINTS = re.compile(
    r"\b(log ?in|sign ?in|verify|verification|account|password|secure|unlock)\b", re.I
)
PAYMENT_HINTS = re.compile(
    r"\b(pay|payment|billing|invoice|refund|checkout|fee|donate)\b", re.I
)
DOMAIN_IN_TEXT = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


@dataclass
class RuleResult:
    score: int
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"score": self.score, "reasons": self.reasons}


def evaluate(parsed: ParsedEmail) -> RuleResult:
    """Score a parsed email. Higher means more phishing signals."""
    reasons: list[str] = []
    points = 0
    rules_fired = 0

    reply_points, reply_reasons = _check_reply_to(parsed)
    if reply_reasons:
        points += reply_points
        rules_fired += 1
        reasons.extend(reply_reasons)

    mismatch_points, mismatch_reasons = _check_link_text(parsed)
    if mismatch_reasons:
        points += mismatch_points
        rules_fired += 1
        reasons.extend(mismatch_reasons)

    urgency_points, urgency_reasons = _check_urgency(parsed.subject, parsed.body)
    if urgency_reasons:
        points += urgency_points
        rules_fired += 1
        reasons.extend(urgency_reasons)

    link_points, link_reasons = _check_payment_or_login(parsed)
    if link_reasons:
        points += link_points
        rules_fired += 1
        reasons.extend(link_reasons)

    bonus = STACK_BONUS.get(rules_fired, 0)
    if bonus:
        reasons.append(
            f"{rules_fired} independent warning signs appear together, which is "
            "much stronger evidence than any one on its own."
        )

    return RuleResult(score=min(100, points + bonus), reasons=reasons)


def _check_reply_to(parsed: ParsedEmail) -> tuple[int, list[str]]:
    """Reply-to on a different domain than the sender is a classic bait-and-switch."""
    if not parsed.reply_to or not parsed.sender_domain:
        return 0, []

    reply_domain = _domain_of(parsed.reply_to)
    if not reply_domain or reply_domain == parsed.sender_domain.lower():
        return 0, []

    return REPLY_TO_MISMATCH, [
        f"Replies would go to {reply_domain}, a different domain from the "
        f"sender's {parsed.sender_domain}."
    ]


def _check_link_text(parsed: ParsedEmail) -> tuple[int, list[str]]:
    """Catch links that show one domain but actually point somewhere else."""
    mismatches = []
    for link in parsed.links:
        text_host = _host_in_text(link.text)
        url_host = _host_of(link.url)
        if text_host and url_host and _clean_host(text_host) != _clean_host(url_host):
            mismatches.append((link, text_host, url_host))

    if not mismatches:
        return 0, []

    link, text_host, url_host = mismatches[0]
    reason = (
        f'Link text says "{text_host}" but the link actually goes to '
        f"{url_host}."
    )
    if len(mismatches) > 1:
        reason += f" {len(mismatches)} links show this mismatch."
    return LINK_TEXT_MISMATCH, [reason]


def _check_urgency(subject: str, body: str) -> tuple[int, list[str]]:
    """Pressure words in the subject or body. Each term counts once."""
    subject_terms = _urgency_terms(subject)
    body_terms = _urgency_terms(body)

    found = []
    for term in subject_terms + body_terms:
        if term not in found:
            found.append(term)

    if not found:
        return 0, []

    points = URGENCY_BY_TERM_COUNT.get(len(found), 20)
    reasons = []
    if subject_terms:
        reasons.append(f"The subject uses urgency language: {_quoted(subject_terms)}.")
    if body_terms:
        reasons.append(f"The message body uses urgency language: {_quoted(body_terms)}.")
    return points, reasons


def _check_payment_or_login(parsed: ParsedEmail) -> tuple[int, list[str]]:
    """A link pushing you to pay or log in is where the damage happens."""
    login_link = None
    payment_link = None

    for link in parsed.links:
        haystack = f"{link.text} {link.url}"
        if login_link is None and LOGIN_HINTS.search(haystack):
            login_link = link
        if payment_link is None and PAYMENT_HINTS.search(haystack):
            payment_link = link
        if login_link and payment_link:
            break

    if not login_link and not payment_link:
        return 0, []

    reasons = []
    if login_link:
        reasons.append(
            f"A link asks you to log in or verify your account "
            f"({login_link.url})."
        )
    if payment_link:
        reasons.append(f"A link asks for a payment ({payment_link.url}).")
    return PAYMENT_OR_LOGIN_LINK, reasons


def _urgency_terms(text: str) -> list[str]:
    if not text:
        return []
    terms = []
    for pattern, label in URGENCY_PATTERNS:
        if pattern.search(text) and label not in terms:
            terms.append(label)
    return terms


def _domain_of(address: str) -> str | None:
    if not address or "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1].strip().lower()
    return domain or None


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _host_in_text(text: str) -> str:
    match = DOMAIN_IN_TEXT.search(text or "")
    return match.group(1).lower() if match else ""


def _clean_host(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _quoted(terms: list[str]) -> str:
    return ", ".join(f"'{term}'" for term in terms)


def _demo() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for path in sorted((root / "examples").glob("*.txt")):
        raw = path.read_text(encoding="utf-8")
        result = evaluate(parse_email(raw))
        print(f"\n{path.name}: score {result.score}/100")
        for reason in result.reasons:
            print(f"  - {reason}")

    # None of the examples has a link whose text disagrees with its target,
    # so check that rule (and full stacking) with a small inline sample.
    print("\ninline sample (all four rules firing):")
    sample = (
        "From: Account Team <support@paypa1-secure.example>\n"
        "Reply-To: help@account-review.example\n"
        "Subject: Urgent: your account is suspended\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        '<p>Act now: <a href="http://login-verify.example/session">'
        "https://www.paypal.com/signin</a></p>"
    )
    result = evaluate(parse_email(sample))
    print(f"  score {result.score}/100")
    for reason in result.reasons:
        print(f"  - {reason}")


if __name__ == "__main__":
    _demo()
