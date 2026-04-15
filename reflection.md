# Reflection

## Profile Comparison Notes

### High-Energy Pop Fan vs. Chill Lofi Listener

These two profiles produce completely opposite results. The pop fan's top 5 is all pop and funk songs with high energy (0.75–0.93) and happy/euphoric moods. The lofi listener's top 5 is all lofi and ambient songs with low energy (0.28–0.42) and chill/focused moods. Not a single song appears in both lists.

This makes sense because the genre bonus (+2.0) is the biggest factor in the scoring formula. Pop and lofi are on completely different ends of the catalog, and the energy preferences (0.85 vs 0.38) pull even further apart. The acoustic preference also plays a role — the lofi listener earns an extra +0.5 for any song with high acousticness, which naturally rewards low-key acoustic songs that a pop fan would never see.

**What this tells me:** Genre is acting as the primary filter. If I removed the genre weight entirely and only scored on energy + mood, the two profiles would probably start sharing some songs (mid-energy happy songs could appear for both). The genre weight is a design choice that makes the system feel more "personalized" but also makes it less likely to surface cross-genre discoveries.

---

### Chill Lofi Listener vs. Deep Intense Rock Head

This was the most extreme contrast. The lofi listener wants calm, acoustic, low-energy music (target energy: 0.38). The rock head wants loud, non-acoustic, high-energy intensity (target energy: 0.92). Their top 5 lists have zero overlap.

What I found interesting is that the rock head's results include punk and metal songs (not just rock) at slots 2–3. The system figured out that punk and metal share the same "intense" mood, high energy, low acousticness, and "aggressive" secondary mood tag as the user's preferences — even without a genre match. The secondary mood tag turned out to be a surprisingly useful feature here.

**What this tells me:** When the preferred genre is rare in the catalog (there's only one rock song), secondary signals like mood and energy take over. The system degrades gracefully — it doesn't break or return nothing, it just shifts to the next best match. That's actually good behavior for a real recommender.

---

### High-Energy Pop Fan vs. Deep Intense Rock Head

Both profiles prefer non-acoustic, high-energy tracks, but their moods are opposite (happy vs. intense). The interesting result here was that **Gym Hero** (a pop song with an "intense" mood) showed up at slot 4 for the rock head. This happened because Gym Hero's energy (0.93) is extremely close to the rock target (0.92), and it carries the "intense" mood — even though it's pop, not rock.

This was the most surprising cross-genre result I observed. It shows that when two features align strongly (energy + mood), a song can break through the genre barrier and appear in an unexpected profile's results.

**What this tells me:** The scoring system can surface cross-genre songs in cases where the sonic features genuinely match. This is actually what good recommendations should do — find music that "feels like" what you want even if it has a different genre label.

---

## Biggest Learning Moment

The weight shift experiment (switching to `energy_focused` mode) showed me how sensitive the output is to a single number. Just by tripling the energy weight, EDM and metal songs suddenly competed with pop for the pop fan's top 3. That change took one line of code but completely changed the personality of the recommender. In a real system, these weights would be learned from user behavior — but even then, someone has to decide what the model is optimizing for.

## What I Would Try Next

1. Make the mood matching fuzzy — "euphoric" should partially match "happy" rather than being a complete miss.
2. Expand the catalog to 100+ songs so niche genres can actually show up meaningfully.
3. Try collaborative filtering as a second pass — after content scoring narrows things down, use what similar users have skipped to rerank the final list.
