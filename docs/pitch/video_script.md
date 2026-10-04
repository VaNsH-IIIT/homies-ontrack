# Demo video script (≤ 5:00, one take per segment, stitched by P1)

**Demo customer:** CRM `VIB-8709` (search by it, or by the case id; golden_id shown on screen), Alberta, English. Linked across **4 systems**: CRM, cards `CX6029150`, loans `B52511750`, core banking CIF `0062157849`.
5 products, total exposure $23,681. **Open case `CS-2026-583749`**: auto loan, 6 days past due, $383.05 overdue, early-stage queue.
On a call they said **"My pay got cut in Aug."** (transcript 4510675).

**Before recording (P1):** `python scripts/run_all.py` all OK · clear test decisions from `decisions.duckdb` · `streamlit run src/ontrack/app/main.py` · browser at 1080p, zoom 110% · warm the Ask cache (`python -m ontrack.l2_ask.warm_demo`; never `run_benchmark` here, it rewrites the committed answers).

| Time | Who | Show | Say |
|---|---|---|---|
| 0:00–0:20 | P1 | Deck cover, then the home page | "In collections, one customer's story is split across five systems. OnTrack joins it up, reads hardship out of notes and calls, and recommends the next best action, with a person always making the call." |
| 0:20–0:40 | P1 | **Home**: 1,015,637 golden customers, Splink precision 99.8% / recall 99.4%, contract 8/8, 19 data issues handled | "Thirty-one raw tables become one trusted customer record. Matching is tested blind on five thousand known links, and the data contract is checked on every build." |
| 0:40–1:00 | P1 | **C360** → search `VIB-8709`: 4 source keys with match method and confidence; accounts; the open case | "Here is one customer: a card, a loan, a bank account and the CRM record, each linked with its evidence and confidence. One open case: an auto loan, six days late." |
| 1:00–1:15 | P1 | **Match review**: pick a grey-zone match, show the masked evidence, approve with a reason | "When the matcher is unsure, it doesn't guess. A data steward sees the evidence, decides, and the next build learns from it." |
| 1:15–2:15 | P2 | **Ask**: `src/ontrack/l2_ask/VIDEO_ASK_SEGMENT.md` | (Garv's voice-over: certified metric + SQL, change a token, RPC by hour, cited policy answer, refusal) |
| 2:15–3:30 | P3 | **Agent card** → `CS-2026-583749`: hardship banner with the quote, recommendation (hardship referral), 3 reasons, counterfactual, blocked actions with their rules; filter Action = call; agent edits with a reason code → history row | `src/ontrack/l4_nba/VIDEO_AGENT_CARD_SEGMENT.md` (2:15–3:30). Fact-checked by Kris (K2, PR #15): the salary claim was false and is replaced by "flagged for reduced income, in the customer's own words". |
| 3:30–4:15 | P3 | `EVALUATION.md`: human-queue split (§4), like-with-like back-test (§2), fairness (§5) | `VIDEO_AGENT_CARD_SEGMENT.md` (3:30–4:15): 62% to a person first; self-cure AUC 0.83 vs 0.72 for the bank's model; fairness gaps within a few points for automated decisions |
| 4:15–5:00 | P1 | **Home → Feedback loop** panel; terminal: `python scripts/run_all.py` summary, all OK | "Every decision and what happened next becomes a label for the next model: 264,285 past decisions already have one. One command rebuilds everything. AI recommends, rules constrain, humans decide, and outcomes improve the next recommendation." |

## Recording checklist
- [x] Kris's PR merged (#11, #12), `[TBD-P3]` lines written
- [x] Every voice-over fact checked against the current build (K2; numbers synced 4 Oct 01:00)
- [ ] Demo run #2 click-through by Vansh
- [ ] Each segment recorded at 1080p (OBS or Xbox Game Bar, `Win+Alt+R`), voice-over clear, no personal data on screen
- [ ] Stitched to ≤ 5:00; uploaded unlisted (YouTube or Drive); link in the README and the submission form
