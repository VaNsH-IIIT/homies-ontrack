# Demo video: four voices, one story (≤ 5:00)

Decided 4 Oct 16:00: **each team member narrates their own part in their own voice**, over silent 1920×1080 screen clips
(already recorded, no bounce at page ends). **Subtitles are burned in** (Clipchamp → Subtitles → Turn on auto subtitles,
English, then fix any misheard word). Fallback only if a segment isn't recorded by 18:00: Clipchamp text-to-speech for
that segment.

**How to record your voice (10 min):** quiet room, phone or laptop mic 15–20 cm away. Open your clip in Clipchamp, press
play, and read your lines with it (Clipchamp → Record & create → Audio, or Windows Voice Recorder). Speak at a calm pace;
~2.3 words a second fits the timings below. Retakes are fine; export the audio as .m4a or .mp3, named `<you>_voice.m4a`.

| Time | Who | Clip (silent) | Length |
|---|---|---|---|
| 0:00–1:15 | **Vansh** | `P1_clipC_cover` (20 s) + `P1_clipA_L1` (trim to 55 s) | 75 s |
| 1:15–2:15 | **Garv** | Garv's Ask clip | 60 s |
| 2:15–3:30 | **Kris** | Kris's `K_clip1_agent_card` (72 s) | 75 s |
| 3:30–5:00 | **Anuj** | Kris's `K_clip3_evaluation` (44 s) + `K_clip2_supervisor_queue` (18 s) + `P1_clipB_close` (28 s) | 90 s |

---

## Vansh: 0:00–1:15, the problem and Layer 1

**0:00 (deck cover):** "In collections, one customer's story is split across five systems. OnTrack joins it up, reads
hardship out of notes and calls, and recommends the next best action, with a person always making the call."

**0:20 (Home):** "Thirty-one raw tables become one trusted record per customer: about one million golden customers.
Matching is tested blind on five thousand known links, at 99.8% precision. A data contract of eight rules is checked on
every build, and twenty data-quality issues are counted and handled."

**0:40 (C360, VIB-8709):** "Here is one customer: a card, a loan, a bank account and the CRM record, each linked with
its evidence and confidence. One open case: an auto loan, six days late. OnTrack already recommends a hardship
referral, in the customer's own words."

**1:00 (Match review):** "When the matcher is unsure, it doesn't guess. A data steward sees masked evidence, decides,
and the next build learns from it."

## Garv: 1:15–2:15, Ask

Follow the "Say" column of `src/ontrack/l2_ask/VIDEO_ASK_SEGMENT.md` (0:00–0:58 on the clip): a certified question with
its SQL, changing a token, the demo customer's call summary, a cited policy answer, and the refusal. Optional last line
if there's room: "Judges can ask it anything live: twenty-one of twenty-one on our dev benchmark, and instant answers
for questions like 'why was this case referred?'"

## Kris: 2:15–3:30, the Agent card

Follow the "Say" lines for **2:15–3:30** in `src/ontrack/l4_nba/VIDEO_AGENT_CARD_SEGMENT.md`: next best action for
every open case; the customer's own words; three plain-English reasons; blocked actions with the rule behind each; the
call queue by dollars at risk; and the agent's decision, logged with a reason.

## Anuj: 3:30–5:00, does it work, does it pay, can people run it?

**3:30 (EVALUATION §2):** "We tested like with like: the same cases on the first of July, outcomes measured after that
date. Our self-cure model scores 0.83 against 0.72 for the bank's own model. Of the cases it says need action now, more
than 99% really did not pay on their own. Of the cases it would leave alone, 53% cured by themselves."

**3:50 (§2b):** "On today's book, that's about 157 thousand dollars more in expected payments per round of contacts,
valued conservatively: median payment, automated cases only."

**4:14 (supervisor view):** "Sixty-two percent of cases go to a person first, so can people cope? The hardship team has
336 agent-hours a day, about 2,200 first contacts, against 490 new referrals. Every new case is reached within a
business day, highest dollars at risk first."

**4:32 (Home → feedback loop → one command):** "Every decision, and what happened next, becomes a label for the next
model: 264,285 past decisions already have one. One command rebuilds everything. AI recommends, rules constrain, humans
decide, and outcomes improve the next recommendation."

---

**Stitch (Clipchamp, ~30 min):** clips in the order above, each person's audio under their clips; trim to the times;
auto subtitles; export 1080p; upload as **unlisted YouTube or Google Drive ("anyone with the link")**; paste the link in
the README and the form. Every number above is from the submission build (`docs/pitch/talk_track.md`, `EVALUATION.md`).
