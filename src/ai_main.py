"""
AI-powered CLI for VibeFinder (Project 4 extension).

Five-step observable pipeline:
  [1] Input guardrail   — validate_input()
  [2] Claude Haiku      — extract_preferences()  (few-shot structured prompting)
  [3] Output guardrail  — validate_preferences() (runs inside step 2)
  [4] Rule-based core   — recommend_songs()      (unchanged from Project 3)
  [5] Claude Haiku      — generate_explanation() (RAG: catalog injected as context)

Usage (from project root):
    python -m src.ai_main "I want chill beats to study"
    python -m src.ai_main -v "heavy metal for the gym"   # verbose step trace
    python -m src.ai_main --demo                          # three built-in queries
    python -m src.ai_main --no-ai                         # base P3 recommender only
    python -m src.ai_main --k 3 "upbeat pop music"        # top-3 instead of top-5
"""

import os
import sys
import argparse
import time

sys.path.insert(0, os.path.dirname(__file__))

from recommender import load_songs, recommend_songs
from ai_recommender import (
    validate_input,
    extract_preferences,
    generate_explanation,
    build_rag_context,
)

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")

DEMO_QUERIES = [
    "I want something high energy for the gym, pumping and loud",
    "Something chill and acoustic to study, maybe lo-fi or jazz",
    "I'm in a nostalgic mood, something sad and slow",
]

_FALLBACK_PREFS = {
    "genre": "pop", "mood": "happy", "energy": 0.75,
    "target_valence": 0.75, "target_danceability": 0.75,
    "likes_acoustic": False, "prefer_popular": True, "secondary_mood": "",
}

TOTAL_STEPS = 5


# ── Formatting helpers ────────────────────────────────────────────────────────

def _sep(char="=", width=70):
    return char * width


def _step(n, name, dur_ms=None, verbose=False):
    if not verbose:
        return
    dur = f"  ({dur_ms:.0f} ms)" if dur_ms is not None else ""
    print(f"  [Step {n}/{TOTAL_STEPS}] {name}{dur}")


def _wrap(text, width=68, indent="  "):
    words = text.split()
    line = indent
    for word in words:
        if len(line) + len(word) + 1 > width:
            print(line)
            line = indent + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)


def _print_recs(recs, k):
    if HAS_TABULATE:
        rows = [
            [i, s["title"], s["artist"], s["genre"], f"{sc:.2f}",
             (exp[:52] + "...") if len(exp) > 55 else exp]
            for i, (s, sc, exp) in enumerate(recs, 1)
        ]
        print(tabulate(
            rows,
            headers=["#", "Title", "Artist", "Genre", "Score", "Reasons"],
            tablefmt="rounded_outline",
        ))
    else:
        for i, (s, sc, exp) in enumerate(recs, 1):
            print(f"  #{i}: {s['title']} by {s['artist']} — {sc:.2f}")
            print(f"       {exp}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(query: str, songs: list, verbose: bool = False, k: int = 5) -> bool:
    """
    Run the full AI + recommender pipeline for a single query.
    Prints results to stdout. Returns True on success.
    """
    print(f"\n{_sep()}")
    print(f'  Query: "{query}"')
    print(_sep())

    # ── Step 1: Input guardrail ───────────────────────────────────────────────
    t0 = time.perf_counter()
    valid, error = validate_input(query)
    _step(1, "Input guardrail — validate_input()", (time.perf_counter()-t0)*1000, verbose)

    if not valid:
        print(f"\n  [GUARDRAIL BLOCKED] {error}")
        return False

    if verbose:
        print(f"  Input accepted.\n")

    # ── Step 2: Claude preference extraction (includes Step 3 guardrail) ──────
    _step(2, "Claude: extract_preferences()  [few-shot structured prompting]",
          verbose=verbose)
    t0 = time.perf_counter()
    prefs, ai_error = extract_preferences(query)
    dur2 = (time.perf_counter() - t0) * 1000
    _step(2, "extract_preferences() done", dur2, verbose)

    # ── Step 3: Output guardrail (runs inside extract_preferences) ────────────
    _step(3, "Output guardrail — validate_preferences()  [auto-ran in step 2]",
          0, verbose)

    if prefs is None:
        print(f"\n  [AI ERROR] {ai_error}")
        print("  Falling back to default profile (pop / happy / energy 0.75).\n")
        prefs = dict(_FALLBACK_PREFS)

    if verbose:
        print(f"  Extracted preferences:")
        for key, val in prefs.items():
            print(f"    {key}: {val}")
        print()

    # ── Step 4: Rule-based recommender ────────────────────────────────────────
    _step(4, "Rule-based recommender — recommend_songs()", verbose=verbose)
    t0 = time.perf_counter()
    recs = recommend_songs(prefs, songs, k=k)
    _step(4, "recommend_songs() done", (time.perf_counter()-t0)*1000, verbose)

    print(f"\n  Top {k} Recommendations:")
    _print_recs(recs, k)

    # ── Step 5: Claude narrative explanation (RAG) ────────────────────────────
    _step(5, "Claude: generate_explanation()  [RAG — catalog as context]",
          verbose=verbose)
    t0 = time.perf_counter()
    catalog_ctx = build_rag_context(songs)
    explanation = generate_explanation(query, recs, catalog_ctx)
    _step(5, "generate_explanation() done", (time.perf_counter()-t0)*1000, verbose)

    if explanation:
        print(f"\n  Why these songs?")
        _wrap(explanation)

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="python -m src.ai_main",
        description="VibeFinder AI — natural language music recommender",
        epilog='Example: python -m src.ai_main "I want chill beats to study"',
    )
    parser.add_argument("query", nargs="*",
                        help="Natural language music request (no quotes needed)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show step-by-step pipeline trace with timings")
    parser.add_argument("--no-ai", action="store_true",
                        help="Skip Claude; run base P3 recommender with demo profiles")
    parser.add_argument("--demo", action="store_true",
                        help="Run three built-in demo queries end-to-end")
    parser.add_argument("--k", type=int, default=5,
                        help="Number of recommendations (default: 5)")
    args = parser.parse_args()

    # ── --no-ai: fall back to the original P3 main ───────────────────────────
    if args.no_ai:
        print("[--no-ai] Running base Project 3 recommender (no Claude).\n")
        import main as p3_main
        p3_main.main()
        return

    songs = load_songs(CSV_PATH)
    print(f"Loaded songs: {len(songs)}")

    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "\n[WARNING] ANTHROPIC_API_KEY is not set.\n"
            "  Claude steps will be skipped; a default profile will be used instead.\n"
            "  To enable AI features:\n"
            "    1. Copy .env.example to .env\n"
            "    2. Fill in your key from https://console.anthropic.com/\n"
            "    3. Re-run this script\n"
        )

    # ── --demo: run all three built-in queries ────────────────────────────────
    if args.demo:
        print(f"\n{_sep('#')}")
        print("  DEMO MODE — three built-in queries")
        print(_sep('#'))
        for query in DEMO_QUERIES:
            run_pipeline(query, songs, verbose=args.verbose, k=args.k)
        return

    # ── Single query from CLI args ────────────────────────────────────────────
    if not args.query:
        parser.print_help()
        print("\nExample queries to try:")
        for q in DEMO_QUERIES:
            print(f'  python -m src.ai_main "{q}"')
        return

    query = " ".join(args.query)
    run_pipeline(query, songs, verbose=args.verbose, k=args.k)


if __name__ == "__main__":
    main()
