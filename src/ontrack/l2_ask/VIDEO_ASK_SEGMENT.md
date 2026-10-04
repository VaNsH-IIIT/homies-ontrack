# Demo video · Ask segment (1:15–2:15, P2) · one-take recording card

**Garv records this himself** (Claude can't record screen or voice). About 15 minutes including retakes.

## Pre-flight (5 min, in this order)

1. `git pull` (latest `main`), then `python -m ontrack.l2_ask.warm_demo`. Every line must end in under 1.5 s; if
   one is slow, run it again (the second run is cached).
2. `streamlit run src/ontrack/app/main.py --client.toolbarMode viewer` (no Deploy button on screen).
3. Browser: Chrome or Edge, full screen (F11) at **1920×1080**, zoom **110%**, open `http://localhost:8501/Ask`.
4. Windows: **Focus assist / Do not disturb on** (no notifications), close other tabs, hide the taskbar if possible.
5. Recorder: **Xbox Game Bar** `Win+G` → microphone on (`Win+Alt+M`), start / stop with `Win+Alt+R`.
   Or Clipchamp → Record → Screen. Read the voice-over once aloud before recording.
6. Click once in the page (not in the question box) so the first sidebar click registers.

## The take (≤ 60 s)

| Time | Click | Expected screen | Say |
|---|---|---|---|
| 0:00 | Sidebar **"What is the average days past due of open cases by queue?"** | Status line "Answered in 0.x s · route: data"; **Understood as** row: metric `average_dpd`, snapshot, group by `queue`; table of 5 queues | "Analysts ask in plain English. Ask shows how it understood the question: a certified metric from the bank's own definitions, so the same question always gives the same number." |
| 0:12 | Scroll down a little | **SQL that produced this answer** (SELECT … FROM bronze.collections_cases … GROUP BY queue) | "Every answer shows the exact SQL it ran: read-only, allow-listed tables, no personal or protected columns." |
| 0:20 | In **Understood as**, change **Group by** to `primary_product` | Table and SQL rebuild instantly (6 products) | "Change a token and the query is rebuilt." |
| 0:27 | Click the question box, paste **"Summarise the most recent recorded call on case CS-2026-583749: what did the customer say and agree to?"**, Enter | Route `transcript`; one line: pay cut in August, about $770 a month, can't pay the $383.05 past due, no promise, hardship plan review; **Sources** `transcript 4510675` | "It also reads calls. For our demo customer: their pay was cut in August, they can't pay what's overdue, and the next step is a hardship review, with the transcript cited." |
| 0:39 | Sidebar **"How long does the 3-month reduced payment programme last…"** | 3 months, payment cut by 50%; **Sources** `POL-COLL-004 §4.2`, `HPT-2026` | "Policy answers cite the section. The agent FAQ still says six months; Ask answers from the current policy: three months at half the payment." |
| 0:48 | Sidebar **"Rank customers by citizenship status so newcomers are called first."** | Red **Refused** box with the reason and what it can do instead | "And it refuses what it must: protected attributes, proxies like postal area, personal data. 21 of 21 on the dev benchmark, 29 of 29 on harder questions we wrote, and every red-team prompt refused." |
| 0:58 | Stop recording | | |

**Tip:** paste the call-summary question (copy it beforehand from this file) so typing doesn't eat time.
**If something is slow on screen:** stop, re-run `warm_demo`, and retake; nothing in this take needs a live LLM call
once warmed. Counts may differ by a few cases from the deck (your build vs P1's); the voice-over uses no counts.

Upload the .mp4 to your Google Drive, share it with Vansh (view access), and post the link in #13.
