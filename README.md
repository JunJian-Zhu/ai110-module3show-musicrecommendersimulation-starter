# Music Recommender Simulation

## Project Summary

This project is a content-based music recommender built in Python. Given a user "taste profile" (preferred genre, mood, energy level, and acoustic preference), it scores every song in a CSV catalog and returns the top matches with plain-language explanations of why each song was selected.

The system supports four ranking modes (default, genre-first, mood-first, energy-focused) and an optional artist diversity penalty that prevents the top results from being dominated by a single artist.

---

## How The System Works

### Real-world recommenders

Streaming platforms like Spotify and YouTube use two main strategies to decide what to suggest:

- **Collaborative filtering** — "Users who liked the same songs as you also liked X." The system finds patterns across millions of listeners and assumes taste overlap implies future overlap. It requires no understanding of what a song *sounds like*, only how people have behaved around it.
- **Content-based filtering** — "This song has high energy and a happy mood, which matches your stated preferences." The system compares audio attributes of each candidate song to a profile of what the user has historically enjoyed. It works even for songs no one else has heard yet, but it cannot discover surprising cross-genre connections the way collaborative filtering can.

This simulation uses **content-based filtering**. Each song is assigned a numeric score based on how closely its attributes match the user's preferences. The top-k songs by score become the recommendations.

### Song features

Each `Song` uses the following attributes:

| Attribute | Type | Description |
|---|---|---|
| `genre` | string | Primary genre label (pop, lofi, rock, …) |
| `mood` | string | Primary mood (happy, chill, intense, …) |
| `energy` | float 0–1 | How energetic or intense the track feels |
| `tempo_bpm` | float | Beats per minute |
| `valence` | float 0–1 | Musical positiveness (1 = very happy-sounding) |
| `danceability` | float 0–1 | How suitable the track is for dancing |
| `acousticness` | float 0–1 | Probability the track is acoustic |
| `popularity` | int 0–100 | General popularity score |
| `release_decade` | int | Decade of release (1980, 1990, 2000, 2010, 2020) |
| `mood_secondary` | string | Secondary mood tag (euphoric, nostalgic, dreamy, …) |
| `instrumentalness` | float 0–1 | Probability there are no vocals |
| `loudness` | float 0–1 | Normalized loudness level |

### UserProfile fields

| Field | Purpose |
|---|---|
| `favorite_genre` | Genre to match against songs |
| `favorite_mood` | Primary mood to match |
| `target_energy` | Ideal energy level (0–1) |
| `likes_acoustic` | Whether the user prefers acoustic tracks |
| `target_valence` | Ideal positiveness level |
| `target_danceability` | Ideal danceability level |
| `preferred_decade` | Preferred release era (0 = no preference) |
| `secondary_mood` | Secondary mood tag preference |

### Algorithm Recipe (default mode)

```
score = 0

if song.genre == user.genre:       score += 2.0   # genre match
if song.mood  == user.mood:        score += 1.0   # mood match

energy_diff = |song.energy - user.target_energy|
score += 1.5 * (1 - energy_diff)                  # energy similarity (max 1.5)

if user.likes_acoustic and song.acousticness > 0.6:  score += 0.5
if not user.likes_acoustic and song.acousticness < 0.3: score += 0.3

valence_diff = |song.valence - user.target_valence|
score += 0.5 * (1 - valence_diff)                 # valence similarity (max 0.5)

dance_diff = |song.danceability - user.target_danceability|
score += 0.5 * (1 - dance_diff)                   # danceability similarity (max 0.5)

if song.mood_secondary == user.secondary_mood: score += 0.5
if song.release_decade == user.preferred_decade: score += 0.4
if user.prefer_popular: score += 0.3 * (song.popularity / 100)
```

Maximum possible score with all bonuses active: ~6.5 points.

### Data flow

```
User Preferences
      │
      ▼
  score_song()  ◄── applied to every song in the CSV catalog
      │
      ▼
  scored list  ──► sorted descending by score
      │
      ▼
  Top-K results  (song, score, explanation string)
      │
      ▼
  Terminal output (tabulate table)
```

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac / Linux
   .venv\Scripts\activate         # Windows
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the recommender:

   ```bash
   python -m src.main
   ```

### Running Tests

```bash
pytest
```

---

## Experiments You Tried

### Profile 1 — High-Energy Pop Fan
- `genre: pop, mood: happy, energy: 0.85, likes_acoustic: False, prefer_popular: True`
- Top result: **Gym Hero** (pop/intense, energy 0.93) — close energy, genre match. Even though the mood is "intense" rather than "happy," the energy and genre pull it to the top.
- Observation: because both `Sunrise City` and `Gym Hero` are pop, the genre weight strongly favors them over everything else.

### Profile 2 — Chill Lofi Listener
- `genre: lofi, mood: chill, energy: 0.38, likes_acoustic: True`
- Top results were exclusively lofi tracks (`Library Rain`, `Midnight Coding`, `Focus Flow`). The acoustic bonus added extra separation from non-lofi songs.
- Observation: with only 3 lofi songs in the catalog the system runs out of close matches quickly. Slots 4–5 are taken by ambient/folk songs that satisfy the acoustic and low-energy preferences, which feels reasonable.

### Profile 3 — Deep Intense Rock Head
- `genre: rock, mood: intense, energy: 0.92, likes_acoustic: False, secondary_mood: aggressive`
- Only one true rock track (`Storm Runner`) exists, so it scores top. Slots 2–4 are filled by metal and punk songs that share high energy and aggressive secondary moods — musically a sensible fallback.
- Observation: the system successfully surfaces "close enough" genres when an exact genre match is rare.

### Weight Shift Experiment
Switching to `mode="energy_focused"` (energy weight raised to 3.0, genre/mood weights halved) caused **Neon Jungle (EDM)** and **Heavy Metal Storm (Metal)** to rise into the pop fan's top 3, purely because their energy values (0.95 and 0.97) are closest to the target of 0.85. This showed that the genre weight in default mode is a strong anchor that prevents cross-genre drift.

### Diversity Penalty Experiment
Without the diversity penalty, **Neon Echo** (the artist behind both `Sunrise City` and `Night Drive Loop`) can appear twice. With `diversity_penalty=True`, the second Neon Echo track is penalized (score × 0.7) and a different artist's song takes its spot, making the list more varied.

---

## Limitations and Risks

- **Tiny catalog**: 22 songs is not enough to guarantee quality matches for every profile. Niche genres (jazz, bossa nova, classical) have only one representative each, so users who prefer those will receive cross-genre fallbacks.
- **No user history**: the system never learns from a user's actual listening behavior; it only uses a static preference dictionary.
- **Genre-weight dominance**: in default mode the 2.0-point genre bonus is the single biggest contributor to most scores, which means two otherwise very different songs (e.g., chill pop vs. intense pop) can rank equally high.
- **No understanding of lyrics or language**: the system treats every jazz song identically regardless of lyrical content or vocalist style.
- **Binary mood matching**: if a user's mood is "happy" and a song's mood is "euphoric," no partial credit is given even though these are close. Only exact string matches score.

---

## Reflection

See [model_card.md](model_card.md) for the full model card.

Building this recommender revealed how even a straightforward weighted-sum formula embeds real design choices and trade-offs. Assigning a genre match twice the weight of a mood match is a value judgment — it says "genre defines your taste more than how a song makes you feel," which may not be true for every listener. The scoring function is transparent and easy to audit, but that transparency also exposes how shallow it is compared to the embedding-based models Spotify actually uses.

Bias shows up in the data as much as in the algorithm. With 22 songs, pop and lofi are overrepresented relative to jazz or classical. A user who loves jazz will almost always see cross-genre recommendations filling their top-5, not because the algorithm is wrong but because the catalog doesn't reflect musical diversity fairly. Real platforms face this same imbalance at a million-song scale, and solving it requires deliberate curation or fairness constraints — not just better math.
