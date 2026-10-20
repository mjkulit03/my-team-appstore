"""Sales Agent (simulated).

Input:  a target customer type.
Output: cold-outreach emails (multiple variants) plus a follow-up sequence.

No LLM involved. Copy is assembled from templates that are selected by the
detected industry and the requested tone, so results are deterministic.
"""

from __future__ import annotations

from . import textkit as tk

VALID_TONES = ("direct", "warm", "consultative")

# Cold emails that run long get truncated. We hold ourselves to this budget.
MAX_EMAIL_WORDS = 150

INDUSTRY_SIGNALS: dict[str, tuple[str, ...]] = {
    "saas & software": ("saas", "software", "platform", "api", "startup", "subscription"),
    "ecommerce & retail": ("retail", "ecommerce", "shop", "store", "merchandise", "clothing"),
    "agencies": ("agency", "consulting", "client", "creative", "freelance", "brand"),
    "professional services": ("consultancy", "law", "legal", "accounting", "advisory", "consulting"),
    "manufacturing": ("manufacturing", "factory", "industrial", "supply", "warehouse"),
    "healthcare": ("clinic", "health", "medical", "patient", "practice", "care"),
    "education": ("school", "university", "college", "training", "education"),
    "finance": ("bank", "finance", "fintech", "insurance", "investment", "lending"),
    "real estate": ("real", "estate", "property", "broker", "mortgage", "rental"),
    "logistics": ("logistics", "freight", "shipping", "fleet", "transport", "warehouse"),
}

# Industry-specific pain point. Written as a noun phrase so the same string fits
# every template slot ("stop X", "cut hours on X", "handling X").
INDUSTRY_PAIN: dict[str, str] = {
    "saas & software": "user onboarding and feature churn",
    "ecommerce & retail": "checkout drop-off and cart abandonment",
    "agencies": "retainer churn and reporting admin",
    "professional services": "unbilled admin work",
    "manufacturing": "status chasing across spreadsheets",
    "healthcare": "scheduling and intake admin",
    "education": "enquiry response and enrolment admin",
    "finance": "manual month-end reconciliation",
    "real estate": "lead follow-up after viewings",
    "logistics": "dispatch exception handling",
}

GENERIC_PAIN = "manual busywork"

# Nouns that read naturally as a direct greeting ("Hi Owner,"). The head noun is
# taken from the end of the phrase, which is where English noun phrases put it.
ROLE_NOUNS = frozenset(
    """
    owner owners manager managers director directors founder founders partner partners
    ceo cto cfo coo president vice team teams lead leader contractor agency
    developer developers engineer engineers designer designers consultant marketers
    seller sellers buyer buyers accountant accountants lawyer lawyers dentist dentists
    physician physicians nurse nurses chef chefs therapist therapists trainer trainers
    coach coaches student students teacher teachers broker brokers realtor realtors
    operator operators editor editors writer writers architect architects freelancer
    freelancers startup startups company companies business smb practice practices
    clinic clinics hospital hospitals store stores shop shops
    """.split()
)


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _greeting_name(audience: str) -> str:
    """Derive a natural salutation from the audience phrase.

    "small dental clinic owners" -> "Owner"; "beekeepers" -> "there".
    """
    tokens = audience.split()
    for token in reversed(tokens):
        candidate = _singular(token)
        if candidate in ROLE_NOUNS:
            return candidate.capitalize()
    return "there"


def _short_audience(audience: str, max_words: int = 3) -> str:
    """A compact segment label for subject lines and body copy."""
    tokens = audience.split()
    if not tokens:
        return "your team"
    if len(tokens) > 2 and tokens[-1].endswith("s"):
        return " ".join(tokens[-2:])
    return " ".join(tokens[:max_words])


VARIANTS = ("direct", "value_first", "question", "social_proof")

TONE_STYLE = {
    "direct": "One ask, one paragraph, no pleasantries.",
    "warm": "Acknowledges their world before making the ask.",
    "consultative": "Leads with a diagnosis and offers a low-risk next step.",
}

VARIANT_LABEL = {
    "direct": "Direct pitch",
    "value_first": "Value first",
    "question": "Question opener",
    "social_proof": "Social proof",
}


def _subjects(product: str, audience: str, variant: str) -> list[str]:
    name = product if len(product) <= 40 else tk.fit(product, 40)
    options = {
        "direct": [f"Quick question, {audience}?", f"{name} \u2014 2 minute demo?", "Worth a short call?"],
        "value_first": [f"Cutting {tk.fit(audience, 20)} admin time", "The admin time sink", "Halving busywork in a week"],
        "question": ["How are you currently handling this?", "Is this on your radar?", "Quick sanity check"],
        "social_proof": [f"{name} results", "What changed after switching", "How similar teams use it"],
    }
    return options[variant]


def _body(variant: str, audience: str, product: str, offer: str, pain: str, sender: str, sender_company: str, tone: str) -> str:
    first_name = _greeting_name(audience)

    if variant == "direct":
        return (
            f"Hi {first_name},\n\n"
            f"We build {product}. It helps {audience} stop {pain}.\n\n"
            f"{offer}\n\n"
            f"Worth 15 minutes next week?\n\n"
            f"{sender}\n{sender_company}"
        )

    if variant == "value_first":
        return (
            f"Hi {first_name},\n\n"
            f"Quick number: teams running {product} cut roughly 5 hours a week on {pain}.\n\n"
            f"We help {audience} do that without a migration project \u2014 most teams are live in a day.\n\n"
            f"{offer}\n\n"
            f"Can I send you the one-page breakdown?\n\n"
            f"{sender}\n{sender_company}"
        )

    if variant == "question":
        return (
            f"Hi {first_name},\n\n"
            f"Out of curiosity \u2014 how are you currently handling {pain}?\n\n"
            f"We work with {audience} and see the same manual process everywhere. "
            f"{product} automates it, and the typical first result shows up in week one.\n\n"
            f"{offer}\n\n"
            f"Happy to just send notes if you're not looking at new tools this quarter.\n\n"
            f"{sender}\n{sender_company}"
        )

    return (
        f"Hi {first_name},\n\n"
        f"Three {audience} teams switched to {product} last quarter and each cut their "
        f"time on {pain} by roughly half.\n\n"
        f"The common factor was that they changed one workflow instead of replacing everything.\n\n"
        f"{offer}\n\n"
        f"Want the two-minute walkthrough?\n\n"
        f"{sender}\n{sender_company}"
    )


def _followups(product: str, offer: str, pain: str) -> list[dict]:
    return [
        {
            "day": 3,
            "channel": "email",
            "purpose": "Add value, no ask",
            "message": (
                f"Sharing this in case it helps: the checklist we use to cut {pain} "
                "without new tooling. No reply needed."
            ),
        },
        {
            "day": 7,
            "channel": "email",
            "purpose": "Break-up email",
            "message": (
                f"Closing the loop \u2014 I haven't heard back, so I'll assume timing is wrong. "
                f"Should I close this out and check back next quarter? If not, reply 'later'."
            ),
        },
        {
            "day": 14,
            "channel": "linkedin",
            "purpose": "Low-effort re-open",
            "message": (
                f"Saw {product} came up in a thread this week. Still on the list, or should "
                "I stop filling your inbox?"
            ),
        },
    ]


def _targeting_notes(industry: str, audience: str) -> list[dict[str, str]]:
    return [
        {
            "point": f"Detected industry: {industry}.",
            "rationale": "Matched from the words in your target customer description; swap the body copy if this is wrong.",
        },
        {
            "point": f"Address the decision-maker as \"{audience}\" rather than \"businesses\".",
            "rationale": "Specific role language raises reply rate because it signals you know their day.",
        },
        {
            "point": "Keep every email under 150 words and ask for one small next step.",
            "rationale": "Long cold emails get skimmed, and multiple asks reduce reply rate.",
        },
        {
            "point": "Send Tuesday to Thursday, 8-10am in the recipient's timezone.",
            "rationale": "Outbound reply rates concentrate early in the work week.",
        },
    ]


def run_sales_agent(
    target_customer_type: str,
    product_name: str = "our product",
    offer: str = "Happy to set up a 15-minute demo with no commitment.",
    sender_name: str = "Alex",
    sender_company: str = "Acme",
    tone: str = "direct",
    variants: int = 3,
) -> dict:
    """Generate cold outreach emails for a target customer type.

    Args:
        target_customer_type: Who to sell to (e.g. \"small dental practices\").
        product_name: Product being pitched.
        offer: The single call to action used in every email.
        sender_name / sender_company: Sign-off details.
        tone: One of ``direct``, ``warm``, ``consultative``.
        variants: How many email variants to produce (1-4).

    Returns:
        A JSON-serialisable dict with ``emails``, ``follow_up_sequence`` and ``targeting_notes``.

    Raises:
        ValueError: on empty customer type, unknown tone, or bad variant count.
    """
    if not target_customer_type or not target_customer_type.strip():
        raise ValueError("target_customer_type is required and cannot be empty")

    audience = " ".join(target_customer_type.strip().split()).lower()
    tone = (tone or "direct").strip().lower()
    if tone not in VALID_TONES:
        raise ValueError(f"tone must be one of {', '.join(VALID_TONES)} (got {tone!r})")

    if not isinstance(variants, int) or isinstance(variants, bool) or not 1 <= variants <= len(VARIANTS):
        raise ValueError(f"variants must be an integer between 1 and {len(VARIANTS)} (got {variants!r})")

    industry = tk.best_label(tk.detected_signals(audience, INDUSTRY_SIGNALS), "general business")
    pain = INDUSTRY_PAIN.get(industry, GENERIC_PAIN)
    product = (product_name or "our product").strip()
    offer_text = (offer or "").strip()

    if not offer_text:
        raise ValueError("offer cannot be empty")

    short_audience = _short_audience(audience)
    emails = []
    for variant in VARIANTS[:variants]:
        body = _body(variant, audience, product, offer_text, pain, sender_name.strip(), sender_company.strip(), tone)
        count = tk.words(body)
        subjects = _subjects(product, short_audience, variant)
        emails.append(
            {
                "variant": variant,
                "label": VARIANT_LABEL[variant],
                "subject_lines": subjects,
                "recommended_subject": subjects[0],
                "subject_length": len(subjects[0]),
                "word_count": count,
                "within_length_budget": count <= MAX_EMAIL_WORDS,
                "personalization_tokens": [audience],
                "body": body,
            }
        )

    return {
        "agent": "sales",
        "target_customer_type": audience,
        "detected_industry": industry,
        "assumed_pain_point": pain,
        "greeting_name": _greeting_name(audience),
        "short_audience_label": short_audience,
        "tone": tone,
        "tone_style": TONE_STYLE[tone],
        "product_name": product,
        "offer": offer_text,
        "emails": emails,
        "follow_up_sequence": _followups(product, offer_text, pain),
        "targeting_notes": _targeting_notes(industry, audience),
        "generated_by": "simulated-rules-engine",
    }