"""
Command line runner for the Music Recommender Simulation.

Run from the project root with:
    python -m src.main

This file demonstrates:
  - Loading songs from CSV
  - Running recommendations for three distinct user profiles
  - Comparing four ranking modes (default, genre_first, mood_first, energy_focused)
  - Showing the diversity penalty in action
"""

import os
import sys

# Ensure the src/ directory is on the path so `import recommender` resolves
sys.path.insert(0, os.path.dirname(__file__))

from recommender import load_songs, recommend_songs

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


# ── Three distinct user profiles ─────────────────────────────────────────────

PROFILES = {
    "High-Energy Pop Fan": {
        "genre": "pop",
        "mood": "happy",
        "energy": 0.85,
        "target_valence": 0.82,
        "target_danceability": 0.85,
        "likes_acoustic": False,
        "prefer_popular": True,
        "secondary_mood": "euphoric",
    },
    "Chill Lofi Listener": {
        "genre": "lofi",
        "mood": "chill",
        "energy": 0.38,
        "target_valence": 0.60,
        "target_danceability": 0.55,
        "likes_acoustic": True,
        "prefer_popular": False,
        "secondary_mood": "focused",
    },
    "Deep Intense Rock Head": {
        "genre": "rock",
        "mood": "intense",
        "energy": 0.92,
        "target_valence": 0.45,
        "target_danceability": 0.65,
        "likes_acoustic": False,
        "prefer_popular": False,
        "secondary_mood": "aggressive",
    },
}


# ── Output helpers ────────────────────────────────────────────────────────────

def _sep(char: str = "=", width: int = 72) -> str:
    return char * width


def print_recommendations(profile_name: str, recs: list, mode: str = "default") -> None:
    """Print a formatted recommendation table for one user profile."""
    label = f"  Profile: {profile_name}"
    if mode != "default":
        label += f"  [mode: {mode}]"
    print(f"\n{_sep()}")
    print(label)
    print(_sep())

    if HAS_TABULATE:
        rows = []
        for rank, (song, score, explanation) in enumerate(recs, 1):
            short_exp = explanation if len(explanation) <= 65 else explanation[:62] + "..."
            rows.append([rank, song["title"], song["artist"], song["genre"], f"{score:.2f}", short_exp])
        print(tabulate(
            rows,
            headers=["#", "Title", "Artist", "Genre", "Score", "Reasons"],
            tablefmt="rounded_outline",
        ))
    else:
        for rank, (song, score, explanation) in enumerate(recs, 1):
            print(f"\n  #{rank}: {song['title']} by {song['artist']}")
            print(f"      Genre: {song['genre']} | Score: {score:.2f}")
            print(f"      Because: {explanation}")


def print_mode_comparison(profile_name: str, prefs: dict, songs: list, k: int = 3) -> None:
    """Compare the top-k results across all four ranking modes for one profile."""
    print(f"\n\n{_sep('#')}")
    print(f"  RANKING MODE COMPARISON  —  {profile_name}")
    print(_sep('#'))

    modes = ["default", "genre_first", "mood_first", "energy_focused"]
    for mode in modes:
        recs = recommend_songs(prefs, songs, k=k, mode=mode)
        print(f"\n  Mode: {mode.upper()}")
        if HAS_TABULATE:
            rows = [[i, s["title"], s["genre"], f"{sc:.2f}"] for i, (s, sc, _) in enumerate(recs, 1)]
            print(tabulate(rows, headers=["#", "Title", "Genre", "Score"], tablefmt="simple"))
        else:
            for i, (s, sc, _) in enumerate(recs, 1):
                print(f"    #{i}: {s['title']} ({s['genre']}) — {sc:.2f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Resolve CSV path relative to the project root (one level above src/)
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")
    songs = load_songs(csv_path)
    print(f"Loaded songs: {len(songs)}")

    # ── 1. Default recommendations for each profile ───────────────────────
    print(f"\n\n{_sep('=')}")
    print("  RECOMMENDATIONS  (default scoring mode)")
    print(_sep('='))

    for name, prefs in PROFILES.items():
        recs = recommend_songs(prefs, songs, k=5)
        print_recommendations(name, recs)

    # ── 2. Ranking mode comparison ────────────────────────────────────────
    pop_prefs = PROFILES["High-Energy Pop Fan"]
    print_mode_comparison("High-Energy Pop Fan", pop_prefs, songs, k=3)

    # ── 3. Diversity mode demo ────────────────────────────────────────────
    print(f"\n\n{_sep('#')}")
    print("  DIVERSITY MODE  (artist repeat penalty applied)")
    print(_sep('#'))
    diverse_recs = recommend_songs(pop_prefs, songs, k=5, diversity_penalty=True)
    print_recommendations("High-Energy Pop Fan", diverse_recs, mode="diversity")


if __name__ == "__main__":
    main()
