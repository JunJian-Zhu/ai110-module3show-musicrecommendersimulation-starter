# Model Card: VibeFinder 1.0

---

## 1. Model Name

**VibeFinder 1.0** — a content-based music recommender simulation

---

## 2. Intended Use

VibeFinder suggests songs from a small catalog based on a user's stated genre preference, mood, energy level, acoustic preference, and a handful of secondary taste signals. It is designed for classroom exploration of how recommendation algorithms work, not for deployment with real users. It assumes each user can be fully described by a single fixed preference dictionary, which is a deliberate simplification.

**Not intended for:** real-time personalization, production streaming services, or any context where a user's privacy or listening history matters.

---

## 3. How the Model Works

Every song in the catalog is given a numeric score that measures how closely it matches what the user said they like. The score is the sum of several smaller checks:

- **Genre match** is worth the most (2 points). If the song's genre matches what the user prefers, they get a big reward.
- **Mood match** is worth 1 point. An exact match on mood (e.g., "happy") gives a bonus.
- **Energy closeness** is worth up to 1.5 points. If the song's energy is very close to the user's target energy on a 0–1 scale, they get close to the full 1.5 points. A song with very different energy gets close to 0.
- **Acoustic preference** gives 0.5 extra points if a user who likes acoustic songs gets an acoustic track, or 0.3 if a user who dislikes acoustic songs gets a non-acoustic one.
- **Valence and danceability** each contribute up to 0.5 points using the same closeness formula as energy.
- **Secondary mood tags**, **release decade**, and **popularity preference** each add small bonuses (0.3–0.5 points) when the song matches the user's extended preferences.

After every song is scored, they are sorted from highest to lowest. The top 5 (or any number k the caller chooses) are returned along with a plain-language explanation of which criteria were met.

Four ranking modes are available: `default` (balanced), `genre_first` (doubles the genre weight), `mood_first` (boosts mood weight 2.5×), and `energy_focused` (triples the energy weight). A diversity penalty mode penalizes any second song by the same artist by 30%, preventing one artist from dominating the list.

---

## 4. Data

- **Catalog size**: 22 songs.
- **Genres represented**: pop, lofi, rock, ambient, jazz, synthwave, indie pop, EDM, folk, hip-hop, classical, funk, metal, bossa nova, indie, R&B, country, electronic, punk.
- **Moods represented**: happy, chill, intense, relaxed, focused, moody, melancholic, nostalgic, romantic, dreamy, energetic.
- **Attributes per song**: 15 (genre, mood, energy, tempo_bpm, valence, danceability, acousticness, popularity, release_decade, mood_secondary, instrumentalness, loudness, plus id/title/artist).
- **Added songs**: 12 original tracks were added to the 10-song starter (Songs 11–22), spanning a wider range of genres and moods not present in the baseline.
- **Data source**: all song data is fabricated for educational purposes. No real streaming metadata was used.
- **Gaps**: pop and lofi have 3 songs each (most represented); jazz, bossa nova, classical, country, and several others have only 1. Users preferring underrepresented genres will receive cross-genre fallbacks.

---

## 5. Strengths

- **Transparency**: every recommendation comes with an explicit list of reasons (e.g., "genre match: pop (+2.0); energy similarity: 1.43/1.50"). There is no black box — the user can see exactly why a song was chosen.
- **Predictability**: because the logic is deterministic and rule-based, the same preferences always produce the same ranking. This makes it easy to debug and explain.
- **Works for well-represented profiles**: users whose preferred genre appears multiple times in the catalog (pop, lofi) consistently receive sensible recommendations.
- **Ranking modes provide flexibility**: switching to `energy_focused` mode lets a user emphasize feel over genre, which can surface unexpected cross-genre suggestions that actually make musical sense.

---

## 6. Limitations and Bias

- **Genre dominance**: the 2.0-point genre bonus is the single largest contributor to most scores. Two pop songs with very different moods and energies can rank much higher than a perfectly matched song from a different genre. This over-prioritizes genre as the defining feature of taste, which is not true for every listener.
- **Small and unbalanced catalog**: pop and lofi are overrepresented (3 songs each). Genres like classical or jazz have a single entry, so a classical fan will almost always see cross-genre songs fill slots 2–5. The recommender is not biased against classical in its logic, but the data imbalance creates a de facto bias in output.
- **Binary mood matching**: "happy" and "euphoric" are treated as completely different moods because the comparison is an exact string match. A song that is close to a user's mood but labeled differently receives no partial credit.
- **Static user profile**: the system cannot learn or update based on what a user skips or replays. Every recommendation session starts fresh from the same fixed preferences.
- **No artist diversity by default**: without the diversity penalty, the same artist can appear multiple times in the top 5 if they have multiple songs that score well, creating a filter bubble around a single artist.
- **No collaborative signal**: because the system knows nothing about what other listeners enjoy, it cannot surface the "you might also like" cross-genre discoveries that make platforms like Spotify feel magical.

---

## 6b. Fairness and Diversity Component

**Problem:** Without any diversity constraint, an artist with two high-scoring songs in the catalog can appear twice in the top 5. This is a fairness issue: it overexposes one artist and underexposes others who may be equally good fits, creating a filter bubble within the results.

**Solution — artist diversity penalty:** When `diversity_penalty=True` is passed to `recommend_songs()`, the function tracks which artists have already been placed in the output. If a song's artist already appears in the top results, that song's score is multiplied by 0.70 (a 30% penalty) before it can fill a remaining slot. This means a repeat artist can still appear if no other song scores high enough, but they are always disadvantaged relative to a new artist.

**Why this improves fairness:**
- It prevents a single prolific artist from monopolizing recommendations simply because they have more songs in the catalog.
- It ensures users are exposed to a wider range of artists, which better reflects the diversity of the available music.
- The penalty is soft (30%, not a hard ban), so a genuinely superior second song from the same artist can still appear — but only if it truly outscores all alternatives after the penalty.

**Trade-off:** The diversity penalty can override musical quality. A slightly lower-scoring song from a new artist may displace a higher-scoring song from a repeat artist. This is intentional — it reflects the deliberate design choice that variety matters, not just pure score maximization.

---

## 7. Evaluation

Three distinct user profiles were tested:

| Profile | Expected behavior | Observed behavior | Verdict |
|---|---|---|---|
| High-Energy Pop Fan | Pop songs with high energy and happy mood on top | Pop songs scored highest; "Gym Hero" (intense mood, not happy) still ranked #1 due to energy + genre | Mostly correct; mood distinction within genre is weak |
| Chill Lofi Listener | Lofi + acoustic, low energy | All 3 lofi tracks ranked 1–3; ambient + folk filled slots 4–5 as logical fallbacks | Correct and intuitive |
| Deep Intense Rock Head | Rock on top; metal/punk as secondary | "Storm Runner" (only rock track) ranked #1; metal/punk correctly filled remaining slots via high energy + aggressive mood tag | Correct |

**Weight shift experiment**: raising the energy weight to 3.0 (`energy_focused` mode) caused EDM and metal tracks to jump into the pop fan's top 3, displacing pop songs that were further from the target energy of 0.85. This confirmed that genre_weight is acting as an anchor preventing cross-genre drift in default mode.

**Diversity experiment**: without the penalty, Neon Echo (artist of both "Sunrise City" and "Night Drive Loop") appeared twice in the pop fan's top 5. With the penalty, "Night Drive Loop" dropped and a different song took its slot, improving variety.

No numeric precision metric was computed; evaluation was qualitative, based on musical intuition and expected vs. observed rank order.

---

## 8. Future Work

1. **Embed moods into a similarity space** rather than requiring exact string matches. A simple lookup table ("euphoric" ≈ "happy" ≈ "energetic") would make the mood comparison much more useful.
2. **Add collaborative filtering as a second pass**. After content-based scoring narrows the list to, say, 20 candidates, a collaborative signal (what do users with similar genre taste also skip?) could rerank the final top 5.
3. **Expand the catalog substantially**. With 200+ songs and more balanced genre coverage, cross-genre fallbacks would be musically meaningful rather than a symptom of data scarcity.
4. **Temporal decay on preferences**: let the user profile weight recent listens more heavily, so the system adapts to mood changes over the course of a day.
5. **Group recommendations**: given two or more user profiles, find songs that maximize the minimum score across all users — useful for shared listening sessions.

---

## 9. Personal Reflection

The biggest surprise was how much one number could change everything. When I switched to `energy_focused` mode and tripled the energy weight, EDM and metal songs suddenly jumped into the top 3 for a pop fan. That shift took one line of code. It made me realize that every weight in the scoring formula is a hidden assumption — "genre matters twice as much as mood" sounds reasonable, but it means a jazz fan who wants high-energy music right now will almost never see an EDM recommendation, because the genre penalty is just too large to overcome.

I also didn't expect the secondary mood tags to matter as much as they did. For the rock head profile, where there's only one actual rock song in the catalog, the system used "intense" mood and "aggressive" secondary tags to pull in punk and metal — which actually felt like the right recommendation. That was the moment where I could see how a real system might work: use multiple overlapping signals instead of relying on a single genre label.

The explainability of this system is something I want to keep in mind going forward. Being able to see "genre match: rock (+2.0); energy similarity: 1.49/1.50; secondary mood: aggressive (+0.5)" for every recommendation makes it easy to understand why a song was chosen and what to change if it doesn't feel right. Most apps hide this completely, which makes them feel smarter than they are but also harder to trust or improve.
