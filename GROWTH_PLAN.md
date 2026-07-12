# Growth Plan — from "content generator" to "self-improving channel"

## Diagnosis (repo + channel audit)

**What the system does well today:** reliable daily generation (CI stable), brand
identity (Anton/yellow), hi-res images with fallback, fact-checking, dedupe,
hashtags, intro card, loudness-normalized audio.

**Why views are low — root causes, ranked:**

| # | Cause | Evidence in repo |
|---|-------|------------------|
| 1 | **No feedback loop.** The agent publishes and never learns. Ideation is a random `niche.yaml` subtopic (Reddit trends mostly 403). Every video is a coin flip. | `_pick_subtopic()` = `random.choice`; no analytics anywhere |
| 2 | **Saturated, undifferentiated niche.** Generic "did you know facts" is the most cloned faceless format on YouTube; the algorithm has thousands of identical channels to choose from. | `niche.yaml` = 15 broad generic subtopics |
| 3 | **Single platform.** YouTube gives new channels the least reach; TikTok/IG Reels give new accounts far more organic distribution. | Only `YouTubePublisher` active |
| 4 | **Retention not engineered or measured.** Retention (avg % viewed) is THE Shorts ranking signal. We don't know where viewers swipe away. The 0.7s static intro card may even hurt (static frame = swipe reflex). | No analytics; intro card untested |
| 5 | **Low data volume.** 1 video/day = 7 data points/week. The algorithm (and we) learn too slowly. Quota allows 6/day. | cron once daily |

**Honest ceiling:** faceless AI fact channels rarely explode; expect 4–8 weeks of
compounding before real signal. Success metric for month 1 is NOT views — it is
**avg % viewed > 70% and week-over-week growth**, which precede views.

---

## Strategy: 4 pillars, in priority order

### Pillar 1 — Close the loop: measure → learn → adapt (highest leverage)
Turn the agent into a system that gets better every day.

1. **Analytics ingestion**: new `infra/analytics.py` pulling per-video
   `views`, `averageViewDuration`, `averageViewPercentage` from the YouTube
   Analytics API. New OAuth scopes (`yt-analytics.readonly`) — re-run
   `scripts/get_youtube_token.py` once.
2. **Stats storage**: `stats` table in `state/history.db` + subtopic and
   variant tags per video (already have `metadata.json`; mirror into DB).
3. **Weekly stats workflow**: a second GitHub Action (Sunday) refreshes stats,
   prints a report (top/bottom videos, retention by subtopic, by hook style),
   commits the DB.
4. **Performance-weighted ideation**: replace `random.choice(subtopics)` with
   70% exploit (best avg-retention subtopics) / 30% explore (unused ones).
   The channel automatically doubles down on what works.

### Pillar 2 — Retention engineering (the ranking signal)
Everything measured via Pillar 1 tags — no guessing.

- **A/B hook styles**: rotate 3 openers (A: "Did you know…", B: shocking claim,
  C: direct question), tag each video, compare retention after 2 weeks.
- **A/B intro card**: alternate on/off per video; the static card may be
  costing the first-second swipe. Data decides.
- **Loop ending**: last narration line hooks back to the opening (rewatches
  count as retention >100%).
- **First 2 seconds**: hook line capped at ~8 words; most striking image first.

### Pillar 3 — Distribution: go where new accounts get reach
- **2 videos/day on YouTube** (cron 10:30 + 17:30 UTC). Doubles learning rate;
  well within quota (2×~1,700 of 10,000 units).
- **TikTok**: register the developer app (code already shipped in
  `providers/publisher.py`). Until approved: manual re-upload of the daily
  `short.mp4` (~2 min/day) — TikTok is where faceless channels actually grow.
- **Instagram Reels** (Meta Graph API) as third target afterwards.

### Pillar 4 — Differentiation: stop being "another facts channel"
- After 2–3 weeks of data: **niche tournament** — take the 2 best-retention
  subtopics and run themed weeks (e.g. "Deep Ocean Week") with series branding
  ("Part 3 of…"). Series drive channel-level watch sessions, which YouTube
  rewards heavily.
- Lock the winning sub-niche as the channel's identity; keep 20% wildcard
  topics for exploration.

---

## Implementation roadmap

| Phase | What ships | Effort |
|-------|-----------|--------|
| **A (now)** | Analytics module + stats table + weekly stats Action + re-auth with analytics scope | 1 session |
| **B** | Variant tagging (hook style / intro card A/B) + loop-ending prompt + 2nd daily cron | small |
| **C** | Performance-weighted ideation (needs ~2 weeks of Phase A data) | small |
| **D** | TikTok (manual now, API when approved) → IG Reels | user + small code |
| **E (week 3–4)** | Niche tournament → lock winning identity | config only |

## KPIs (check weekly, in the stats report)
- Avg % viewed (target: >70%) — the leading indicator
- Views per video, week over week
- Best/worst subtopic and hook style by retention
- Subs per 1k views (CTA effectiveness)
