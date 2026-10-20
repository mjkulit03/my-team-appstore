"""Small deterministic text helpers shared by the simulated agents.

Everything here is deliberately naive and side-effect free so the agents stay
reproducible: the same input always yields the same output.
"""

from __future__ import annotations

import re

WORD_RE = re.compile(r"[a-z0-9']+")

# Generic verbs and adverbs that appear in almost every product description. Left
# in, they poison generated copy ("covers accounting, automates, commerce").
GENERIC_VERBS = frozenset(
    """
    automate automates automated handle handles managing manage manages provide provides
    providing help helps make makes making sync syncs synced build builds building create
    creates creating let lets allow allows enable enables giving give gives take takes
    save saves saving track tracks tracking connect connects integrate integrates
    offer offers offering deliver delivers replace replaces simplify simplifies reduce
    reduces improving improve improves increase increases work works use uses using need
    needs want wants come comes go goes get gets getting see sees looking look looks
    turn turns turning convert converts match matches bring brings bring put puts
    """.split()
)

# Descriptive adjectives and filler nouns: meaningless inside a product name.
GENERIC_ADJECTIVES = frozenset(
    """
    small large big tiny huge new old best better good great easy simple smart powerful
    fast quick quicker modern custom complete full real actual unique dedicated
    professional advanced flexible seamless robust reliable affordable popular
    """.split()
)

GENERIC_ADVERBS = frozenset(
    """
    directly instantly automatically seamlessly simply easily quickly effortlessly
    immediately thoroughly virtually basically actually instantly reliably accurately
    freely happily fully completely perfectly properly exactly
    """.split()
)

NON_NOUN_SUFFIXES = ("ing",)

# Category words describe the *kind* of thing, not its name. Used when guessing
# a product name so we never return "Saas Platform" as a brand name.
GENERIC_TECH_NOUNS = frozenset(
    """
    saas platform software app application service services tool tools system systems
    solution solutions product products website web business company online based
    devtool devtools framework engine extension add-on
    """.split()
)

STOPWORDS = frozenset(
    """
    a an the and or but if then than that this these those of in on at to for
    with from by as is are was were be been being it its we you they them us
    their our your my me he she his her do does did done have has had having
    will would can could should shall may might must not no nor so such about
    into over under again more most other some any all each few there here
    when where why how very just also now new get got make made use used
    lot lots way ways thing things bit bits stuff bunch kind sort etc
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens."""
    return WORD_RE.findall((text or "").lower())


def is_noise(word: str) -> bool:
    """True for words too generic to be used as a feature/message pillar."""
    return (
        len(word) < 3
        or word.isdigit()
        or word in STOPWORDS
        or word in GENERIC_VERBS
        or word in GENERIC_ADVERBS
        or word in GENERIC_ADJECTIVES
        or word.endswith(NON_NOUN_SUFFIXES)
    )


def top_keywords(text: str, limit: int = 8) -> list[str]:
    """Most frequent *substantive* words, tie-broken alphabetically.

    Filters generic verbs/adverbs, which otherwise dominate the frequency count
    and produce nonsensical copy such as "covers accounting, automates, commerce".
    """
    counts: dict[str, int] = {}
    for word in tokenize(text):
        if is_noise(word):
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:limit]]


def hashtags_from(keywords: list[str], limit: int = 5) -> list[str]:
    """Turn keywords into deduped, tag-safe hashtags."""
    tags: list[str] = []
    for word in keywords:
        tag = "#" + re.sub(r"[^a-z0-9]", "", word)
        if len(tag) > 2 and tag not in tags:
            tags.append(tag)
    return tags[:limit]


def fit(text: str, limit: int) -> str:
    """Truncate on a word boundary, appending an ellipsis when shortened."""
    text = (text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or text[: limit - 1]) + "\u2026"


def fit_with_tail(body: str, tail: str, limit: int) -> str:
    """Fit ``body`` while guaranteeing ``tail`` (e.g. hashtags) survives intact."""
    body = (body or "").strip()
    tail = (tail or "").strip()
    combined = f"{body} {tail}".strip() if tail else body
    if limit <= 0 or len(combined) <= limit:
        return combined
    if not tail:
        return fit(body, limit)
    room = limit - len(tail) - 1
    if room <= 0:
        return fit(tail, limit)
    trimmed = fit(body, room)
    if not trimmed:
        return tail
    return f"{trimmed} {tail}".strip()


def title_from_description(description: str, max_words: int = 3) -> str:
    """Best-effort product name: the leading *distinctive* content words.

    Filters generic verbs, adverbs and category words, and caps the length, so a
    bare description yields "Invoice Reconciliation" rather than a run-on phrase.
    """
    words = [w for w in tokenize(description) if not is_noise(w) and w not in GENERIC_TECH_NOUNS]
    chosen = words[:max_words]
    if not chosen:
        return "Your Product"
    return " ".join(w.capitalize() for w in chosen)


def words(text: str) -> int:
    return len(tokenize(text))


def money(amount: float) -> str:
    """Render a float as a human-readable currency-ish string."""
    return f"${amount:,.2f}"


def detected_signals(text: str, signals: dict[str, tuple[str, ...]]) -> dict[str, int]:
    """Count how many of each signal group appear in ``text``."""
    haystack = " ".join(tokenize(text))
    hits: dict[str, int] = {}
    for label, needles in signals.items():
        found = sum(1 for needle in needles if needle in haystack)
        if found:
            hits[label] = found
    return hits


def best_label(hits: dict[str, int], fallback: str) -> str:
    """Highest-scoring label, ties broken alphabetically."""
    if not hits:
        return fallback
    return sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]