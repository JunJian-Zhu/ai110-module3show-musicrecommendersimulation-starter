"""
AI layer for VibeFinder (Project 4 extension).

Provides three capabilities on top of the existing rule-based recommender:
  1. extract_preferences()   — Claude Haiku converts natural language into
                               a structured preference dict (few-shot prompting)
  2. generate_explanation()  — Claude Haiku writes a narrative explanation
                               grounded in the actual song catalog (RAG)
  3. validate_input() /      — Input and output guardrails that run before
     validate_preferences()    and after every Claude call

Each Claude call is observable: callers receive a (result, error) tuple
so failures can be logged, displayed, or fallen back from gracefully.
"""

import os
import json
import re

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Model and valid-value sets ────────────────────────────────────────────────

MODEL = "claude-haiku-4-5-20251001"

VALID_GENRES = {
    "pop", "lofi", "rock", "edm", "folk", "hip-hop", "classical",
    "funk", "metal", "bossa nova", "indie", "r&b", "country",
    "electronic", "punk", "jazz", "synthwave", "ambient", "indie pop", "any",
}

VALID_MOODS = {
    "happy", "chill", "intense", "relaxed", "focused", "moody",
    "melancholic", "nostalgic", "romantic", "dreamy", "energetic", "any",
}

_INJECTION_PHRASES = [
    "ignore previous", "disregard", "system:", "```",
    "forget your instructions", "new instructions", "jailbreak",
]


# ── System prompts ────────────────────────────────────────────────────────────

_EXTRACTOR_SYSTEM = """\
You are a music preference extraction assistant. Given a natural language music
request, return ONLY a valid JSON object — no explanation, no markdown fences,
no extra text before or after the JSON.

Required JSON schema:
{
  "genre": string,
  "mood": string,
  "energy": float 0.0-1.0,
  "likes_acoustic": boolean,
  "target_valence": float 0.0-1.0,
  "target_danceability": float 0.0-1.0,
  "secondary_mood": string or ""
}

Valid genres: pop, lofi, rock, edm, folk, hip-hop, classical, funk, metal,
  bossa nova, indie, r&b, country, electronic, punk, jazz, synthwave,
  ambient, indie pop, any

Valid moods: happy, chill, intense, relaxed, focused, moody, melancholic,
  nostalgic, romantic, dreamy, energetic, any

Valid secondary moods: euphoric, nostalgic, dreamy, aggressive, romantic,
  chill, focused, or empty string ""

--- FEW-SHOT EXAMPLES ---

Request: "I want something super chill to study to, maybe lo-fi beats"
{"genre":"lofi","mood":"chill","energy":0.35,"likes_acoustic":true,"target_valence":0.55,"target_danceability":0.50,"secondary_mood":"focused"}

Request: "Give me high energy bangers to work out, heavy bass"
{"genre":"edm","mood":"intense","energy":0.92,"likes_acoustic":false,"target_valence":0.70,"target_danceability":0.90,"secondary_mood":"euphoric"}

Request: "I'm feeling sad and nostalgic, something acoustic and soft"
{"genre":"indie","mood":"melancholic","energy":0.32,"likes_acoustic":true,"target_valence":0.28,"target_danceability":0.40,"secondary_mood":"nostalgic"}

Request: "Heavy metal for when I'm angry"
{"genre":"metal","mood":"intense","energy":0.95,"likes_acoustic":false,"target_valence":0.30,"target_danceability":0.60,"secondary_mood":"aggressive"}

Request: "Fun dance music for a party"
{"genre":"pop","mood":"happy","energy":0.88,"likes_acoustic":false,"target_valence":0.85,"target_danceability":0.90,"secondary_mood":"euphoric"}
"""

_EXPLAINER_SYSTEM = """\
You are a friendly music curator. Given a listener's request and a ranked list
of recommended songs (with their genre, mood, and energy attributes), write a
warm, specific 2-3 sentence explanation of why these songs were chosen.
Reference actual song attributes — be concrete, not generic.
Do not re-list the songs. End on an enthusiastic note.
"""


# ── Guardrail 1: Input validation ─────────────────────────────────────────────

def validate_input(query: str) -> tuple:
    """
    Check the user query before sending it to Claude.
    Returns (is_valid: bool, reason: str).
    """
    if not query or not query.strip():
        return False, "Query cannot be empty."
    stripped = query.strip()
    if len(stripped) < 5:
        return False, "Query is too short. Describe the kind of music you want."
    if len(query) > 500:
        return False, "Query is too long (max 500 characters)."
    if stripped.replace(" ", "").isdigit():
        return False, "Query must contain words, not just numbers."
    lower = query.lower()
    for phrase in _INJECTION_PHRASES:
        if phrase in lower:
            return False, f"Query contains disallowed content: '{phrase}'."
    return True, ""


# ── Guardrail 2: Output (preference) schema validation ────────────────────────

def validate_preferences(prefs: dict) -> tuple:
    """
    Validate that Claude's extracted preference dict matches the expected schema.
    Returns (is_valid: bool, reason: str).
    Mutates prefs in place: coerces genre/mood to lowercase and applies
    graceful fallback for unknown genre/mood values.
    """
    required = ["genre", "mood", "energy", "likes_acoustic",
                "target_valence", "target_danceability"]
    for field in required:
        if field not in prefs:
            return False, f"Missing required field: '{field}'"

    for float_field in ["energy", "target_valence", "target_danceability"]:
        val = prefs[float_field]
        if not isinstance(val, (int, float)):
            return False, f"'{float_field}' must be a number, got {type(val).__name__}"
        if not 0.0 <= float(val) <= 1.0:
            return False, f"'{float_field}' must be 0.0–1.0, got {val}"

    if not isinstance(prefs["likes_acoustic"], bool):
        return False, f"'likes_acoustic' must be true/false, got {prefs['likes_acoustic']!r}"

    # Normalise string fields
    prefs["genre"] = str(prefs.get("genre", "any")).lower().strip()
    prefs["mood"] = str(prefs.get("mood", "any")).lower().strip()
    prefs["secondary_mood"] = str(prefs.get("secondary_mood", "")).lower().strip()

    # Graceful fallback: unknown genre/mood → "any" (recommender ignores non-matches)
    if prefs["genre"] not in VALID_GENRES:
        prefs["genre"] = "any"
    if prefs["mood"] not in VALID_MOODS:
        prefs["mood"] = "any"

    return True, ""


# ── RAG context builder ───────────────────────────────────────────────────────

def build_rag_context(songs: list) -> str:
    """
    Convert the song catalog into a compact text block.
    This is injected verbatim into Claude's explanation prompt so the model
    can reference real song titles and attributes (retrieval-augmented generation).
    """
    lines = [f"Song catalog ({len(songs)} tracks):"]
    for s in songs:
        lines.append(
            f"  • {s['title']} by {s['artist']} | genre={s['genre']} | "
            f"mood={s['mood']} | energy={s['energy']:.2f} | "
            f"valence={s['valence']:.2f} | acoustic={s['acousticness']:.2f} | "
            f"secondary={s.get('mood_secondary', '')}"
        )
    return "\n".join(lines)


# ── Step 1: Preference extraction via Claude ──────────────────────────────────

def extract_preferences(query: str) -> tuple:
    """
    Send the user query to Claude Haiku and extract structured music preferences.

    This is the few-shot structured prompting step (Specialization stretch).
    The system prompt contains five labeled examples that teach Claude the exact
    JSON schema before it sees the real query.

    Returns (prefs_dict, error_string).
    On success: prefs_dict is a validated dict, error_string is "".
    On failure: prefs_dict is None, error_string explains why.
    """
    if not _ANTHROPIC_AVAILABLE:
        return None, "anthropic package not installed. Run: pip install anthropic"

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, (
            "ANTHROPIC_API_KEY is not set.\n"
            "  Fix: export ANTHROPIC_API_KEY='sk-ant-...'\n"
            "  Or copy .env.example to .env and fill in your key."
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=_EXTRACTOR_SYSTEM,
            messages=[{
                "role": "user",
                "content": f'Request: "{query}"\nResponse:',
            }],
        )
        raw = message.content[0].text.strip()

    except anthropic.AuthenticationError:
        return None, (
            "API key rejected (401 Unauthorized).\n"
            "  Check that ANTHROPIC_API_KEY is correct.\n"
            "  Get a valid key at: https://console.anthropic.com/"
        )
    except anthropic.APIConnectionError as exc:
        return None, f"Could not reach Claude API: {exc}"
    except Exception as exc:
        return None, f"Unexpected API error: {type(exc).__name__}: {exc}"

    # Parse JSON — direct parse first, regex extraction as fallback
    prefs = None
    try:
        prefs = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            try:
                prefs = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if prefs is None:
        return None, f"Could not parse JSON from Claude response: {raw!r}"

    # Run output guardrail
    valid, error = validate_preferences(prefs)
    if not valid:
        return None, f"Output guardrail blocked: {error}"

    return prefs, ""


# ── Step 2: Narrative explanation via Claude (RAG) ────────────────────────────

def generate_explanation(query: str, recs: list, catalog_context: str) -> str:
    """
    Use Claude Haiku to write a narrative explanation of why the recommended
    songs match the user's request.

    The full song catalog is passed as RAG context so Claude can reference
    real song attributes rather than hallucinating details.

    Returns the explanation string, or a plain-text fallback on failure.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not _ANTHROPIC_AVAILABLE or not api_key:
        titles = ", ".join(s["title"] for s, _, _ in recs[:3])
        return f"[AI explanation unavailable] Top picks: {titles}"

    rec_lines = "\n".join([
        f"  {i}. {s['title']} by {s['artist']} "
        f"(genre={s['genre']}, mood={s['mood']}, energy={s['energy']:.2f}, "
        f"score={sc:.2f})"
        for i, (s, sc, _) in enumerate(recs, 1)
    ])

    user_msg = (
        f"Listener's request: \"{query}\"\n\n"
        f"Recommended songs (ranked):\n{rec_lines}\n\n"
        f"{catalog_context}\n\n"
        "Explain in 2-3 sentences why these songs match the listener's request."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=_EXPLAINER_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        return message.content[0].text.strip()
    except Exception:
        titles = ", ".join(s["title"] for s, _, _ in recs[:3])
        return f"[AI explanation unavailable] Top picks: {titles}"
