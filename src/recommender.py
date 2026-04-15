from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
import csv


@dataclass
class Song:
    """Represents a song and its attributes."""
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float
    # Extended attributes (optional, with defaults for backward compatibility)
    popularity: int = 50
    release_decade: int = 2010
    mood_secondary: str = ""
    instrumentalness: float = 0.1
    loudness: float = 0.5


@dataclass
class UserProfile:
    """Represents a user's taste preferences."""
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool
    # Extended preferences (optional)
    target_valence: float = 0.7
    target_danceability: float = 0.7
    preferred_decade: int = 0   # 0 = no preference
    secondary_mood: str = ""


class Recommender:
    """OOP implementation of the recommendation logic."""

    def __init__(self, songs: List[Song]):
        self.songs = songs

    def _score_song_obj(self, user: UserProfile, song: Song) -> Tuple[float, List[str]]:
        """Score a Song object against a UserProfile and return (score, reasons)."""
        score = 0.0
        reasons = []

        # Genre match: +2.0
        if song.genre.lower() == user.favorite_genre.lower():
            score += 2.0
            reasons.append(f"genre match: {song.genre} (+2.0)")

        # Mood match: +1.0
        if song.mood.lower() == user.favorite_mood.lower():
            score += 1.0
            reasons.append(f"mood match: {song.mood} (+1.0)")

        # Energy similarity: up to 1.5 points (closer = higher score)
        energy_diff = abs(song.energy - user.target_energy)
        energy_score = round(1.5 * (1.0 - energy_diff), 4)
        score += energy_score
        reasons.append(f"energy similarity: {energy_score:.2f}/1.50")

        # Acousticness preference
        if user.likes_acoustic and song.acousticness > 0.6:
            score += 0.5
            reasons.append("acoustic match (+0.5)")
        elif not user.likes_acoustic and song.acousticness < 0.3:
            score += 0.3
            reasons.append("non-acoustic preference (+0.3)")

        # Valence similarity: up to 0.5 points
        valence_diff = abs(song.valence - user.target_valence)
        valence_score = round(0.5 * (1.0 - valence_diff), 4)
        score += valence_score
        reasons.append(f"valence similarity: {valence_score:.2f}/0.50")

        # Secondary mood tag match: +0.5
        if user.secondary_mood and song.mood_secondary:
            if song.mood_secondary.lower() == user.secondary_mood.lower():
                score += 0.5
                reasons.append(f"secondary mood match: {song.mood_secondary} (+0.5)")

        return round(score, 4), reasons

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Return top k songs sorted by score (highest first) for the given user profile."""
        scored = [(song, self._score_song_obj(user, song)[0]) for song in self.songs]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [song for song, _ in scored[:k]]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Return a human-readable explanation for why a song was recommended."""
        _, reasons = self._score_song_obj(user, song)
        if not reasons:
            return "No specific match found."
        return "; ".join(reasons)


def load_songs(csv_path: str) -> List[Dict]:
    """Load songs from a CSV file, converting numeric fields to their proper types."""
    songs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            songs.append({
                "id": int(row["id"]),
                "title": row["title"],
                "artist": row["artist"],
                "genre": row["genre"],
                "mood": row["mood"],
                "energy": float(row["energy"]),
                "tempo_bpm": float(row["tempo_bpm"]),
                "valence": float(row["valence"]),
                "danceability": float(row["danceability"]),
                "acousticness": float(row["acousticness"]),
                # Extended attributes (gracefully handle older CSVs without them)
                "popularity": int(row.get("popularity", 50)),
                "release_decade": int(row.get("release_decade", 2010)),
                "mood_secondary": row.get("mood_secondary", ""),
                "instrumentalness": float(row.get("instrumentalness", 0.1)),
                "loudness": float(row.get("loudness", 0.5)),
            })
    return songs


def score_song(
    user_prefs: Dict,
    song: Dict,
    mode: str = "default",
) -> Tuple[float, List[str]]:
    """
    Score a single song against user preferences using weighted rules.

    Scoring recipe (default mode):
      +2.0  genre match
      +1.0  mood match
      +1.5  energy similarity (scaled: 1.5 * (1 - |song_energy - target_energy|))
      +0.5  acoustic match (if user likes_acoustic and song.acousticness > 0.6)
      +0.3  non-acoustic preference (if not likes_acoustic and acousticness < 0.3)
      +0.5  valence similarity (scaled: 0.5 * (1 - |valence_diff|))
      +0.5  danceability similarity (if target_danceability in prefs)
      +0.5  secondary mood tag match
      +0.4  release decade match (if preferred_decade in prefs)
      +0.3  popularity bonus (if prefer_popular is True)

    Ranking modes adjust genre/mood/energy weights:
      genre_first   — genre weight x2, others halved
      mood_first    — mood weight x2.5, genre and energy reduced
      energy_focused — energy weight x2, genre and mood reduced

    Returns (score, reasons) where reasons is a list of explanation strings.
    """
    score = 0.0
    reasons = []

    # ── Weight presets by mode ──────────────────────────────────────────────
    genre_w, mood_w, energy_w = 2.0, 1.0, 1.5
    if mode == "genre_first":
        genre_w, mood_w, energy_w = 4.0, 0.5, 0.75
    elif mode == "mood_first":
        genre_w, mood_w, energy_w = 1.0, 2.5, 1.0
    elif mode == "energy_focused":
        genre_w, mood_w, energy_w = 1.0, 0.5, 3.0

    # ── Genre match ─────────────────────────────────────────────────────────
    if song.get("genre", "").lower() == user_prefs.get("genre", "").lower():
        score += genre_w
        reasons.append(f"genre match: {song['genre']} (+{genre_w:.1f})")

    # ── Mood match ──────────────────────────────────────────────────────────
    if song.get("mood", "").lower() == user_prefs.get("mood", "").lower():
        score += mood_w
        reasons.append(f"mood match: {song['mood']} (+{mood_w:.1f})")

    # ── Energy similarity ───────────────────────────────────────────────────
    target_energy = user_prefs.get("energy", 0.5)
    energy_diff = abs(song["energy"] - target_energy)
    energy_score = round(energy_w * (1.0 - energy_diff), 4)
    score += energy_score
    reasons.append(f"energy similarity: {energy_score:.2f}/{energy_w:.2f}")

    # ── Acousticness preference ─────────────────────────────────────────────
    if user_prefs.get("likes_acoustic", False) and song.get("acousticness", 0) > 0.6:
        score += 0.5
        reasons.append("acoustic match (+0.5)")
    elif not user_prefs.get("likes_acoustic", True) and song.get("acousticness", 0) < 0.3:
        score += 0.3
        reasons.append("non-acoustic preference (+0.3)")

    # ── Valence similarity ──────────────────────────────────────────────────
    if "target_valence" in user_prefs:
        valence_diff = abs(song["valence"] - user_prefs["target_valence"])
        valence_score = round(0.5 * (1.0 - valence_diff), 4)
        score += valence_score
        reasons.append(f"valence similarity: {valence_score:.2f}/0.50")

    # ── Danceability similarity ─────────────────────────────────────────────
    if "target_danceability" in user_prefs:
        dance_diff = abs(song["danceability"] - user_prefs["target_danceability"])
        dance_score = round(0.5 * (1.0 - dance_diff), 4)
        score += dance_score
        reasons.append(f"danceability similarity: {dance_score:.2f}/0.50")

    # ── Secondary mood tag match ────────────────────────────────────────────
    if user_prefs.get("secondary_mood") and song.get("mood_secondary"):
        if song["mood_secondary"].lower() == user_prefs["secondary_mood"].lower():
            score += 0.5
            reasons.append(f"secondary mood match: {song['mood_secondary']} (+0.5)")

    # ── Release decade preference ───────────────────────────────────────────
    if user_prefs.get("preferred_decade") and song.get("release_decade"):
        if song["release_decade"] == user_prefs["preferred_decade"]:
            score += 0.4
            reasons.append(f"decade match: {song['release_decade']}s (+0.4)")

    # ── Popularity bonus ────────────────────────────────────────────────────
    if user_prefs.get("prefer_popular", False) and "popularity" in song:
        pop_score = round(0.3 * (song["popularity"] / 100), 4)
        score += pop_score
        reasons.append(f"popularity bonus: {pop_score:.2f}/0.30")

    return round(score, 4), reasons


def recommend_songs(
    user_prefs: Dict,
    songs: List[Dict],
    k: int = 5,
    mode: str = "default",
    diversity_penalty: bool = False,
) -> List[Tuple[Dict, float, str]]:
    """
    Score all songs, apply an optional artist diversity penalty, and return the top k results.

    Returns a list of (song_dict, score, explanation_string) tuples sorted by score descending.
    """
    # Score every song
    scored = []
    for song in songs:
        song_score, reasons = score_song(user_prefs, song, mode=mode)
        explanation = "; ".join(reasons) if reasons else "No specific match"
        scored.append((song, song_score, explanation))

    # Sort highest score first
    scored.sort(key=lambda x: x[1], reverse=True)

    if not diversity_penalty:
        return scored[:k]

    # ── Diversity penalty: cap one song per artist in the top results ────────
    seen_artists: set = set()
    top_results: List[Tuple[Dict, float, str]] = []
    overflow: List[Tuple[Dict, float, str]] = []

    for song, song_score, explanation in scored:
        artist = song.get("artist", "")
        if artist not in seen_artists:
            top_results.append((song, song_score, explanation))
            seen_artists.add(artist)
            if len(top_results) == k:
                break
        else:
            penalized_score = round(song_score * 0.7, 4)
            overflow.append((song, penalized_score, explanation + " [artist repeat penalty]"))

    # Fill remaining slots from penalized overflow if top_results < k
    if len(top_results) < k:
        overflow.sort(key=lambda x: x[1], reverse=True)
        top_results.extend(overflow[: k - len(top_results)])

    return top_results[:k]
