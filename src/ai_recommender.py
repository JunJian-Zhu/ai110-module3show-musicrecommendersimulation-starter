"""
AI layer for VibeFinder (Project 4 extension).

Uses Google Gemini (gemini-2.0-flash, free tier) instead of Anthropic Claude.
Get a free API key at: https://aistudio.google.com/apikey

Provides three capabilities on top of the existing rule-based recommender:
  1. extract_preferences()   — Gemini converts natural language into a
                               structured preference dict (few-shot prompting)
  2. generate_explanation()  — Gemini writes a narrative explanation
                               grounded in the actual song catalog (RAG)
  3. validate_input() /      — Input and output guardrails that run before
     validate_preferences()    and after every Gemini call
"""

import os
import json
import re

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Model and valid-value sets ────────────────────────────────────────────────

MODEL = "gemini-2.0-flash"

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
    Check the user query before sending it to Gemini.
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
    Validate that Gemini's extracted preference dict matches the expected schema.
    Returns (is_valid: bool, reason: str).
    Coerces genre/mood to lowercase and applies graceful fallback for unknowns.
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

    prefs["genre"] = str(prefs.get("genre", "any")).lower().strip()
    prefs["mood"] = str(prefs.get("mood", "any")).lower().strip()
    prefs["secondary_mood"] = str(prefs.get("secondary_mood", "")).lower().strip()

    if prefs["genre"] not in VALID_GENRES:
        prefs["genre"] = "any"
    if prefs["mood"] not in VALID_MOODS:
        prefs["mood"] = "any"

    return True, ""


# ── RAG context builder ───────────────────────────────────────────────────────

def build_rag_context(songs: list) -> str:
    """
    Convert the song catalog into a compact text block injected into Gemini's
    explanation prompt (retrieval-augmented generation).
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


def _get_client():
    """Create and return a Gemini client, or raise with a helpful message."""
    if not _GENAI_AVAILABLE:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.\n"
            "  Get a FREE key at: https://aistudio.google.com/apikey\n"
            "  Then: export GEMINI_API_KEY='your-key-here'\n"
            "  Or add it to your .env file."
        )
    return genai.Client(api_key=api_key)


# ── Step 1: Preference extraction via Gemini ──────────────────────────────────

def extract_preferences(query: str) -> tuple:
    """
    Send the user query to Gemini and extract structured music preferences.

    Uses few-shot structured prompting: the system prompt contains five labeled
    examples that teach Gemini the exact JSON schema before it sees the real query.

    Returns (prefs_dict, error_string).
    On success: prefs_dict is a validated dict, error_string is "".
    On failure: prefs_dict is None, error_string explains why.
    """
    try:
        client = _get_client()
    except RuntimeError as exc:
        return None, str(exc)

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=f'Request: "{query}"\nResponse:',
            config=types.GenerateContentConfig(
                system_instruction=_EXTRACTOR_SYSTEM,
                max_output_tokens=256,
                temperature=0.1,
            ),
        )
        raw = response.text.strip()

    except Exception as exc:
        msg = str(exc)
        if "API_KEY_INVALID" in msg or "invalid" in msg.lower():
            return None, (
                "Gemini API key is invalid.\n"
                "  Get a free key at: https://aistudio.google.com/apikey"
            )
        return None, f"Gemini API error: {type(exc).__name__}: {msg}"

    # Parse JSON — direct parse first, regex fallback second
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
        return None, f"Could not parse JSON from Gemini response: {raw!r}"

    valid, error = validate_preferences(prefs)
    if not valid:
        return None, f"Output guardrail blocked: {error}"

    return prefs, ""


# ── Step 2: Narrative explanation via Gemini (RAG) ────────────────────────────

def generate_explanation(query: str, recs: list, catalog_context: str) -> str:
    """
    Use Gemini to write a narrative explanation of why the recommended songs
    match the user's request. The full catalog is passed as RAG context.

    Returns the explanation string, or a fallback string on failure.
    """
    if not _GENAI_AVAILABLE or not os.getenv("GEMINI_API_KEY", ""):
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
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=_EXPLAINER_SYSTEM,
                max_output_tokens=300,
                temperature=0.7,
            ),
        )
        return response.text.strip()
    except Exception:
        titles = ", ".join(s["title"] for s, _, _ in recs[:3])
        return f"[AI explanation unavailable] Top picks: {titles}"
