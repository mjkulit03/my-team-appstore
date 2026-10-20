"""Marketing Agent (simulated).

Input:  a product description.
Output: per-channel social posts plus strategy points.

No LLM involved. The output is derived deterministically from the description so
the module is testable and free to run.
"""

from __future__ import annotations

from . import textkit as tk

VALID_TONES = ("confident", "friendly", "bold", "technical")

# Character budgets per channel. Real networks enforce these, so we do too.
CHANNEL_LIMITS: dict[str, int] = {
    "x": 280,
    "linkedin": 3000,
    "instagram": 2200,
    "facebook": 63206,
}

CATEGORY_SIGNALS: dict[str, tuple[str, ...]] = {
    "saas": ("software", "platform", "api", "dashboard", "saas", "cloud", "integration", "automation", "workflow", "app", "subscription"),
    "ecommerce": ("shop", "store", "cart", "checkout", "shipping", "retail", "clothing", "apparel", "merchandise"),
    "devtools": ("developer", "code", "api", "sdk", "repository", "compile", "debug", "open", "source", "cli", "library"),
    "fintech": ("banking", "payment", "invoice", "finance", "accounting", "expense", "budget", "ledger", "billing"),
    "healthcare": ("health", "patient", "clinic", "medical", "care", "wellness", "therapy", "diagnosis"),
    "education": ("course", "student", "learning", "school", "teach", "training", "curriculum"),
    "agency": ("agency", "client", "consulting", "campaign", "brand", "creative", "freelance"),
    "manufacturing": ("factory", "manufacturing", "industrial", "supply", "warehouse", "production", "hardware"),
    "realestate": ("property", "real", "estate", "listing", "rent", "mortgage", "home", "tenant"),
    "food": ("food", "recipe", "meal", "restaurant", "kitchen", "delivery", "coffee", "grocery"),
}

AUDIENCE_SIGNALS: dict[str, tuple[str, ...]] = {
    "developers": ("developer", "engineer", "devops", "programmer", "technical", "api"),
    "small businesses": ("small", "business", "smb", "startup", "founder", "entrepreneur", "owner", "shop"),
    "enterprise teams": ("enterprise", "corporate", "procurement", "compliance", "security", "it", "operations"),
    "creators": ("creator", "influencer", "audience", "content", "blogger", "artist"),
    "consumers": ("consumer", "customer", "everyday", "personal", "home", "family"),
    "students": ("student", "university", "college", "campus"),
}

TONE_LEADS = {
    "confident": "Clear, benefit-led, no hype.",
    "friendly": "Warm and plain-spoken, like a helpful teammate.",
    "bold": "Punchy and contrarian, opens with a challenge.",
    "technical": "Precise and specific, leads with mechanism and numbers.",
}

TONE_CTA = {
    "confident": "Start your free trial",
    "friendly": "See how it works",
    "bold": "Stop guessing. Try it",
    "technical": "Read the docs",
}

# Extra strategy advice that depends on what we detected about the product.
CATEGORY_PLAYBOOK: dict[str, list[str]] = {
    "saas": [
        "Lead with a 30-second demo clip; SaaS buyers convert on seeing the workflow, not reading about it.",
        "Publish one case study with a concrete before/after metric \u2014 it is the highest-intent asset for this category.",
    ],
    "ecommerce": [
        "Run a creator-code affiliate push; for physical goods this beats cold ads on first-purchase CAC.",
        "Retarget anyone who viewed a product page but did not check out.",
    ],
    "devtools": [
        "Publish an install-to-first-success snippet; developers abandon anything that takes longer than five minutes to run.",
        "Sponsor the relevant newsletter or conference talk rather than running broad display ads.",
    ],
    "fintech": [
        "Lead with the audit trail and security posture, not the price.",
        "Publish plain-language explainers for the accounting rules you automate \u2014 it builds the trust fintech buyers need.",
    ],
    "healthcare": [
        "Everything must pass clinical and compliance review before scheduling; keep claims conservative.",
        "Publish anonymised outcomes data, since buyers discount vendor claims in this category.",
    ],
    "education": [
        "Free tier or student plan converts fastest; it seeds the next cohort.",
        "Post instructor testimonials \u2014 the instructor is the real buyer.",
    ],
    "agency": [
        "Sell the outcome the client reports upward (retention, CAC, revenue), not the process.",
        "Offer a scoped pilot; agencies avoid long procurement cycles for unproven tools.",
    ],
    "manufacturing": [
        "Lead with uptime and integration specs; procurement filters on those first.",
        "Publish a total-cost-of-ownership worksheet so operations can justify the spend internally.",
    ],
    "realestate": [
        "Use listing-level visuals; the first photo decides whether anything else gets read.",
        "Target landlords and property managers with direct mail \u2014 high intent, low volume.",
    ],
    "food": [
        "Post the food, not the brand voice; UGC of the actual product outperforms designed creative.",
        "Run a weekly offer tied to a seasonal moment to keep repeat purchase cadence up.",
    ],
}

GENERIC_PLAYBOOK = [
    "Post three times a week minimum: one problem post, one proof post, one offer post.",
    "Reply to every comment in the first hour \u2014 that window drives most reach on small accounts.",
    "Repurpose the best-performing post into the next month's email rather than writing new copy.",
]


def _hooks(name: str, audience: str, keywords: list[str], tone: str, index: int) -> str:
    subject = keywords[index % len(keywords)] if keywords else "the work"
    options = {
        "confident": [
            f"{name} is the simplest way to handle {subject}.",
            f"{subject}, without the busywork.",
            f"Meet {name}: built for {audience} who need {subject} handled.",
        ],
        "friendly": [
            f"Hi \u2014 if {subject} is eating your week, this is for you.",
            f"We built {name} so you never have to think about {subject} again.",
            f"A calmer way to deal with {subject}.",
        ],
        "bold": [
            f"{subject.capitalize()} should not take a whole afternoon.",
            f"Stop tolerating a broken {subject} process.",
            f"Most tools get {subject} wrong. {name} doesn't.",
        ],
        "technical": [
            f"{name} handles {subject} deterministically \u2014 no manual steps.",
            f"Under the hood: automated {subject} with full audit output.",
            f"{name} reduces {subject} to one configured rule.",
        ],
    }
    variants = options[tone]
    return variants[index % len(variants)]


def _body(name: str, keywords: list[str], index: int) -> str:
    picks = keywords[index : index + 3] or ["the essentials"]
    feature_list = ", ".join(picks)
    tail = (
        f"{name} covers {feature_list} in one place, "
        "so your team spends its time on the work that actually needs a human."
    )
    return tk.fit(tail, 400)


def _channel_shape(channel: str, name: str, audience: str, keywords: list[str], tone: str, index: int) -> str:
    hook = _hooks(name, audience, keywords, tone, index)
    body = _body(name, keywords, index)
    cta = TONE_CTA[tone]
    if channel == "x":
        return f"{hook}\n\n{body}\n\n{cta} \u2192 {name.lower().replace(' ', '')}.com"
    if channel == "linkedin":
        return f"{hook}\n\n{body}\n\nHere's who it's for: {audience}.\n\n{cta}.\n\nWhat broke first when you tried to scale this?"
    if channel == "instagram":
        return f"{hook}\n\n{body}\n\n{cta} \u2014 link in bio.\n\nSave this for the next time {subject_of(keywords)} comes up."
    return f"{hook}\n\n{body}\n\n{cta}: {name}"


def subject_of(keywords: list[str]) -> str:
    return keywords[0] if keywords else "the work"


def _tags_for(channel: str, keywords: list[str], limit: int) -> list[str]:
    # Instagram rewards a small, tight tag set; wider channels tolerate more.
    count = {"instagram": 5, "x": 2, "linkedin": 3, "facebook": 2}[channel]
    return tk.hashtags_from(keywords, limit=min(count, limit))


def _build_strategy(
    category: str,
    audience: str,
    keywords: list[str],
    hashtags: list[str],
    tone: str,
    brand: str | None,
) -> list[dict[str, str]]:
    strategy: list[dict[str, str]] = [
        {
            "point": f"Position against {category.replace(' ', ' ')} alternatives on one axis only.",
            "rationale": (
                f"The description reads as {category}, and buyers in this space shortlist on a "
                "single differentiator. Pick the axis (speed, price, accuracy) and repeat it everywhere."
            ),
        },
        {
            "point": f"Write for {audience} in the first sentence of every post.",
            "rationale": f"{audience.capitalize()} self-identify fast; naming them stops the scroll immediately.",
        },
        {
            "point": "Use these three message pillars consistently: " + ", ".join(keywords[:3] or ["core value"]) + ".",
            "rationale": "Derived from the most frequent terms in the product description, so it reflects what you actually built.",
        },
        {
            "point": f"Use a {tone} voice: {TONE_LEADS[tone]}",
            "rationale": "Set once in the brief so five different posts still sound like one brand.",
        },
        {
            "point": "Give every post one link and one call to action.",
            "rationale": "Multiple competing asks measurably reduce click-through on small accounts.",
        },
        {
            "point": "Caption with " + " ".join(hashtags[:3] or ["#launch"]) + " and rotate the rest weekly.",
            "rationale": "A stable tag set keeps the account discoverable; a rotating tail avoids spam flags.",
        },
    ]
    for advice in CATEGORY_PLAYBOOK.get(category, GENERIC_PLAYBOOK):
        strategy.append({"point": advice, "rationale": f"Playbook rule for {category}."})
    if brand:
        strategy.insert(
            0,
            {
                "point": f"Attach the {brand} brand assets to every asset before publishing.",
                "rationale": "Requested brand was supplied; consistent visual identity compounds recognition.",
            },
        )
    return strategy


def run_marketing_agent(
    product_description: str,
    product_name: str | None = None,
    brand: str | None = None,
    tone: str = "confident",
    channels: list[str] | None = None,
) -> dict:
    """Generate social posts and strategy points for a product description.

    Args:
        product_description: What the product does. Required, non-empty.
        product_name: Optional override; inferred from the description otherwise.
        brand: Optional brand name recorded in the strategy output.
        tone: One of ``confident``, ``friendly``, ``bold``, ``technical``.
        channels: Subset of ``x``, ``linkedin``, ``instagram``, ``facebook``.

    Returns:
        A JSON-serialisable dict with ``posts`` and ``strategy``.

    Raises:
        ValueError: on empty input, unknown tone, or unknown channel.
    """
    if not product_description or not product_description.strip():
        raise ValueError("product_description is required and cannot be empty")
    if len(product_description.strip()) < 20:
        raise ValueError("product_description is too short to generate useful marketing copy (need 20+ characters)")

    tone = (tone or "confident").strip().lower()
    if tone not in VALID_TONES:
        raise ValueError(f"tone must be one of {', '.join(VALID_TONES)} (got {tone!r})")

    selected = [c.strip().lower() for c in (channels or list(CHANNEL_LIMITS)) if c and c.strip()]
    unknown = [c for c in selected if c not in CHANNEL_LIMITS]
    if unknown:
        raise ValueError(f"unknown channel(s): {', '.join(unknown)}; valid: {', '.join(CHANNEL_LIMITS)}")
    if not selected:
        raise ValueError("at least one channel is required")

    description = product_description.strip()
    name = (product_name or tk.title_from_description(description)).strip()
    keywords = tk.top_keywords(description, limit=10)
    category = tk.best_label(tk.detected_signals(description, CATEGORY_SIGNALS), "general")
    audience = tk.best_label(tk.detected_signals(description, AUDIENCE_SIGNALS), "busy professionals")

    posts = []
    for index, channel in enumerate(selected):
        limit = CHANNEL_LIMITS[channel]
        tags = _tags_for(channel, keywords, limit)
        tail = " ".join(tags)
        raw = _channel_shape(channel, name, audience, keywords, tone, index)
        # Hashtags always go last, so a length trim can never drop them.
        combined = tk.fit_with_tail(raw, tail, limit)
        full_length = len(raw) + (1 + len(tail) if tail else 0)
        posts.append(
            {
                "channel": channel,
                "char_limit": limit,
                "char_count": len(combined),
                "within_limit": len(combined) <= limit,
                "truncated": full_length > limit,
                "hashtags": tags,
                "post": combined,
            }
        )

    hashtags = tk.hashtags_from(keywords, limit=6)
    return {
        "agent": "marketing",
        "product_name": name,
        "detected_category": category,
        "detected_audience": audience,
        "tone": tone,
        "keywords": keywords[:8],
        "hashtags": hashtags,
        "posts": posts,
        "strategy": _build_strategy(category, audience, keywords, hashtags, tone, brand),
        "generated_by": "simulated-rules-engine",
    }