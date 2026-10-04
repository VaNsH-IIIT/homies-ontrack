# Task board

Owned by **P1 (Vansh)**. Do only the tasks with your ID, only inside your folders (see the ownership table in [README](README.md#team-and-ownership)).
Status: `[ ]` to do · `[~]` in progress · `[x]` merged to `main`. Update your own rows in your PR.

**Tasks say what must work, not how.** The "Done when" column and the interfaces in the README are fixed; the approach inside your folders is yours: choose libraries, prompts, features and models, and experiment. Fixed regardless: the table names and columns in the interfaces, the hackathon rules (no protected attributes, a plain-English reason for every decision, human review, hardship flagged), and the design as the base (log any change and why).

## 🏆 Competition push (4 Oct 13:30 → 16:00; code stop 17:30)

Judging: technical quality and working demo (incl. benchmark and **live unseen questions**) · business understanding · innovation · teamwork · presentation.

| ID | Who | Task | Done when | By |
|---|---|---|---|---|
| G20 | **Garv's Claude** | Deterministic "explain case <id>" and "tell me about customer <id>" in Ask (from gold + nba, SQL shown, no PII, no LLM), example buttons, tests | < 1 s, 0 LLM calls; tests pass | 15:00 |
| G21 | **Garv's Claude** | Live-question resilience: LLM slow or failing → clear message and the closest certified answer, never a traceback or a long spinner | Tests for timeout and usage limit | 15:30 |
| G22 | **Garv's Claude** | `src/ontrack/l2_ask/QA_NOTES.md`: judge Q&A for Layers 2/3 | One page, numbers checked | 15:30 |
| K24 | **Kris's Claude** | `$` escaping on the Agent card (as in #41) | Email/SMS cases render dollars correctly | 14:00 |
| K25 | **Kris's Claude** | "62% go to a person: can agents cope?": human queue by reason and dollars, priority order, workload vs capacity, 1-business-day feasibility (EVALUATION + supervisor view + QA_NOTES) | Generated section + card line | 15:30 |
| K26 | **Kris's Claude** | Run P1's live-question set through Ask on Kris's allowance; misses to Garv | Score table posted | 15:30 |
| V14 | **P1-Claude** | Live-question set (~30 judge-style questions, all layers, answers from independent SQL) | In `docs/rehearsal/` | 14:15 |
| V15 | **P1-Claude** | `docs/QA_L1.md`: Layer 1 judge Q&A | One page | 15:00 |
| V16 | **P1-Claude** | README "How we worked" with real numbers (PRs, reviews, findings) | In README | 15:00 |

## 🎯 Final hardening until 16:00 (posted 4 Oct, 06:15 IST): read this first

All code tasks so far are merged (#15–#28; 231 tests). Until **16:00** we close the remaining risks; deck, PDF and video come **after 16:00**, all together.

| ID | Who | Task | Done when | By |
|---|---|---|---|---|
| ✅ V8 | **P1-Claude** (15 questions in docs/rehearsal/, 06:30) | **C360 / data-quality question set:** ~15 questions a judge may ask about Layer 1 (golden customers, matching, duplicates, DQ counts, contract), each with the correct answer from independent SQL. Saved as `benchmark/rehearsal_c360.csv` (+ answers) and posted in #13 | 15 questions + verified answers on `main` | 11:00 |
| ✅ G12 | **Garv** | Run V8's set through Ask; fix every miss in `l2_ask/` with tests; score posted on the PR | 15/15 (or each miss explained); dev still 21/21 | 14:00 |
| V9 | **Vansh, after 11:00** | **19:00 dress rehearsal** by hand on cached questions: normalise → `run_benchmark` → `score_dev` → commit (to a test branch). Checklist from P1-Claude | Runs from the checklist alone, 0 errors, < 10 min | 13:00 |
| ✅ G13 | **Garv** (#29 merged) | **Backup runner** for 19:00: same steps ready on Garv's machine with his own Claude access, tested on cached questions | Garv can produce a full `answers.csv` within 15 min of a failure | 16:00 |
| V10 | **Vansh, after 11:00** (P1-Claude does a headless pass first) | **Browser click-through** of the whole demo path (`docs/pitch/video_script.md`): fix list of anything slow, confusing or ugly, posted in #13 | List posted; P1 pages fixed by P1-Claude, P2/P3 items routed to Garv/Kris | 12:00 |
| ✅ K12 | **Kris** (#30: tried 7, model kept) | **Payment-within-7-days model, time-boxed 2 h:** try to lift AUC 0.58 (behaviour after past contacts, link opens, payday timing). Merge only if test AUC +0.03 or more, K1 determinism holds, no other number moves unexpectedly; else document why in `EVALUATION.md` | PR with before/after, or a documented "tried, kept" | 12:00 |
| ✅ K13 | **Kris** (#31 merged) | **Judge Q&A note** `src/ontrack/l4_nba/QA_NOTES.md`: why AUC 0.83 and not higher, calibration drift, the separated-group fairness gap, why calls stay a policy, what "+$163K per round" means and doesn't | One page; reviewed and approved by Vansh (V11) | 15:00 |
| V11 | **Vansh, after 11:00** | **Lead review:** read and approve K13 and G12 (P1-Claude prepares the full-data checks) | Both approved on GitHub by Vansh | 15:00 |
| V12 | **Vansh, after 11:00** | Decide judge access to the private repo | Decisions in #13 | 09:00 |
| V13 | **Vansh, after 11:00** | Rehearse the P1 voice-overs (0:00–1:15, 4:15–5:00), no recording yet | Read through twice, timed | 16:00 |
| ✅ G14 | **Garv's Claude** | Recording card for Garv's 16:00 take (clicks, screens, time stamps, pre-flight); warm_demo covers every question shown | Card in `VIDEO_ASK_SEGMENT.md`, step times tested | 10:00 |
| ✅ G15 → K21 | **Garv's Claude** | Final regression on `main` after all merges: dev 35 + hard 29 + L1 8 + V8 + mock extras | Scores posted, 0 errors | 10:30 |
| ✅ G16 | **Kris's Claude** (#37; 343 pass with and without data) | `test_l2_guards.py`: the PII-name test passes with and without the dataset (monkeypatch `sql_guard._TAGGED`; Kris's finding) | `pytest` all pass on a clone with no `.env` and with full data | 10:00 |
| ✅ G17 | **Garv's Claude** (#39) | Backup path can't drop the released 35: runbook uses normalize --append-released + scratch --out + check_submission; `backup_run.validate()` fails if any BQ-001..035 is missing (+ test) | PR merged | 14:00 |
| ✅ K14 | **Kris's Claude** (#32 merged) | Recording card for Kris's 16:00 take; every voice-over number checked on `main`; screens fit 1920×1080 | Card in `VIDEO_AGENT_CARD_SEGMENT.md` | 10:00 |
| ✅ K15 | **Kris's Claude** | Judge fresh-clone re-test on the latest `main` (K9 again), now and again after the 20:00 freeze | All OK, `git status` clean, check_submission passes | 07:30 |
| ✅ K16 | **Kris's Claude** | Peer review of today's P1 changes (app router, C360, Match review, check_submission, deliverable_path, V8 generator) | Findings posted in #13; P1-Claude fixes | 09:00 |
| ✅ K17 | **Kris's Claude** (#34: ranker 49%→95%) | Test gaps in L4 / L3-structured (coverage); add tests for the important untested functions, no behaviour change | PR with coverage before/after | 10:30 |
| ✅ K18 | **Kris's Claude** | README as a judge reads it: find each deliverable / result / quick start in 30 s; stale or jargon lines; concrete edits posted for P1 | Suggestions in #13; P1 edits | 09:00 |
| ✅ K19 | **Kris's Claude** (#35: policy gate 100%, 31/31 mutations) | Coverage for `l3_features/structured` and `policy_gate.py`; tests only, 96,000-row diff proves no behaviour change | PR with coverage before/after | 10:30 |
| ✅ K20 | **Kris's Claude** | Test gaps in P1 code (`l1_factory`, `feedback`), tests only, authorised by P1; bugs posted for P1 to fix | PR with coverage before/after | 11:00 |
| ✅ C1 | **P1-Claude** (all OK, 06:25) | Full end-to-end run on `main` with all merges (app stopped): run_all, pytest, every page, demo path | All OK, or each break fixed / routed | 08:00 |
| ✅ C2 | **P1-Claude** (clean; requirements-lock.txt added) | Repo hygiene: no secrets, data or large files; `.gitignore`, requirements | Clean, or fixed | 08:30 |

**After 16:00 (everyone):** recordings (G4, K4, Vansh's segments) → stitch → deck final numbers + PDF → 19:00 benchmark → 20:00 freeze → submit by 20:30.

## ☀️ 4 Oct plan from P1: read this first (updated 4 Oct, 00:45 IST)

**State:** PRs #15 and #17 (Kris: K1 repeatable training, K2 video facts, K3 edge cases, "Why this channel" card, fairness by group) are verified on full data and merged. Checks: pytest 197, `run_all --skip-l1` all OK, dev 21/21, all 5 pages load. Open: **#16 (K5)** and Garv's branch `p2/P2-G-polish` (G2, G3), which has no PR yet.
**Numbers source:** the deck, README and video quote **P1's build**, because P1's machine produces the submission. On `main` now: 96,000 open cases · human-only **59,942 (62%)** · hardship referral **46,235 (48%)** · text-only hardship **8,883** · calls **5,037** · self-cure AUC **0.83** vs bank **0.72**. Your own machine may differ by a few cases, because it has a different LLM cache. In voice-overs, say "62%", "about 46,000" and "nearly 9,000" rather than exact counts.

| ID | Who | Task | Done when | By |
|---|---|---|---|---|
| ✅ G6 | **Garv** | (#21 merged 01:45: G1 3 fresh runs stable after ask-v8, G2 dry run 50 answers in 132 s with 0 errors, G3 hardening) | Open a PR for `p2/P2-G-polish` (G2 `--retry-failed`, G3 Ask hardening) and post the **G1** result (3 fresh runs) in #13 | PR open, the peer-merge checks in the description, G1 diff posted | 10:00 |
| ✅ K5 | **Kris** | #16 (merged 01:00, keyed on DPD 151–180 → `p_charge_off_risk`, 4,000 cases; 92,000 keep `p_roll_forward`): P1 approved the design (`p_roll_forward` NULL for `180+`, new `p_charge_off_risk`, `current_bucket`). Rebase on `main`, mark it ready, add full-data counts | 180+ count and top-5 of each list in the PR; pytest and `run_all --skip-l1` OK | 10:00 |
| ✅ K7 | **Kris** | (#19 merged 01:25) Add `model_risk_rank` to `gold.nba_recommendation` (1 = most likely to stay unpaid, from the raw score; the calibrated probabilities tie at ≈1.0) | No existing column, action or AUC changes; new top 5 of each list in the PR | 10:00 |
| ✅ G5 | **Garv** | (#21) | #16 is merged. R5 roll-forward: order by the probability `DESC NULLS LAST`, then `model_risk_rank` (K7; `overdue_now DESC` until K7 merges), then `case_id` (24,458 cases tie at ≈1.0, so the tie-break decides the top 10); add the example "which open cases are closest to charge-off?" on `p_charge_off_risk` | Both questions answer with SQL on the Ask page; dev still 21/21 | 12:00 |
| — | **Garv ↔ Kris** | Review each other's PRs (#16, G6) with the 🌙 peer-merge checks; P1 merges | Check results posted on the PR | 12:00 |
| ✅ G8 | **Garv** | (#22 merged 01:50) | One-line follow-up to #21: lists show `r.current_bucket` (from DPD), not the stale source label `c.current_bucket`; then `warm_demo` | Charge-off list never shows "180+" below DPD 181 | 10:00 |
| ✅ K10 | **Kris** (for Garv, who is rate-limited; table on #13: 4 failures for G10) | **G10 test half:** run `run_benchmark` with **no LLM** (only certified-metric and refusal questions answer; the others print 'no LLM') on variants of the questions file: UTF-8 BOM, CRLF, columns reordered, `metric_id` / `as_of_date` columns missing, an extra column, blank lines, a duplicate id, commas and quotes inside a question. Don't edit `l2_ask/` (P2's folder): post a table in #13 of variant → result (OK, or the traceback) | Garv fixes the failures when he's back; a test file of the variants can go in `tests/test_l2_*` in Garv's PR | 06:00 |
| ✅ K11 | **Kris** (takes over G11; corrections applied in `a937bb4` + deck v13) | **Fresh-eyes review** of `docs/pitch/OnTrack_pitch_deck.pdf`, all 10 slides, plus the README Submission section and `docs/pitch/video_script.md` (P1 segments 0:00–1:15, 4:15–5:00): every number against P1's build (`gold.*`, `EVALUATION.md`, `docs/data_quality_report.md`, Garv's L2 numbers in `BENCHMARK_NOTES.md` / #21 / #23). Post corrections in #13 (P1 edits; read-only for you) | Every number confirmed or corrected with its source | 06:00 |
| ✅ G10 | **Garv** | (#28 merged 06:00; 231 tests; 15/15 file variants OK) K10 found: cp1252 crash, header spaces, semicolons, duplicate ids (details on #13). (Testing done by Kris, K10) **19:00 file robustness:** run `run_benchmark` (no LLM: certified and refusal questions only, or a mocked LLM) on variants of the questions file: UTF-8 BOM, CRLF, columns in another order, missing `metric_id` / `as_of_date` columns, extra columns, blank lines, a duplicate id, quotes and commas inside a question. Fix anything that breaks; add the variants as tests | One answers row per unique id for every variant, no crash; tests in `tests/test_l2_*` | 12:00 |
| ✅ K9 | **Kris** | (report on #13; #26 merged; P1 fixed README + deliverable overwrite in `a43c673`; Kris re-tests the clone) | **Judge's fresh-clone test:** `git clone` into a new folder, a **new** venv, `pip install -r requirements.txt && pip install -e .`, then only the README quick start on the 5% sample. Report every step that fails or is unclear (P1 fixes README) | The README alone gets a new machine from clone to the app, no extra installs | 12:00 |
| ~~G11~~ | **Garv** | (moved to Kris, K11) **Fresh-eyes review** of `docs/pitch/OnTrack_pitch_deck.pdf` slides 5–6 and README rows for Layer 2/3 against your latest numbers (29/29, ask-v9, notes recall 0.97). Post corrections in #13 (P1 edits) | Every L2/L3 number in deck and README confirmed or corrected | 12:00 |
| G4 | **Garv (in person, not Claude)** | Record the Ask segment (1:15–2:15), 1080p, ≤ 60 s; steps in #13; `warm_demo` first. Drive link to P1 | File received by P1 | **14:00** |
| ✅ K8 | **Kris** | (#24 merged 03:25; P1 build: +$163,457 per round) | **Business value in dollars** (business is 20% of the score; slide 8 has only percentages): from the back-test and channel economics, compute a conservative, data-backed CAD figure for the open book, e.g. contact cost saved by leaving likely self-cures alone, plus expected recovery from the act-now cases, vs the bank's last recommendation. State the method and every assumption in a new `EVALUATION.md` section, generated by `evaluation.py` | One number per lever with its method; P1 puts the total on slide 8 | 12:00 |
| K4 | **Kris (in person, not Claude)** | Record the Agent card + evaluation segment (2:15–4:15), 1080p, ≤ 2:00; steps in #13. The checked script in `VIDEO_AGENT_CARD_SEGMENT.md`; can show "Why this channel" | File received by P1 | **14:00** |
| G7 | **Garv** | Online 18:45–19:45 for the final benchmark run (`BENCHMARK_NOTES.md` runbook). Fix only code, never `answers.csv` | 0 errors in the final run | 19:45 |
| K6 | **Kris** | Online 19:45–20:30: after the final `run_all` on P1's machine, P1 regenerates `EVALUATION.md` there (`python -m ontrack.l4_nba.evaluation`) and you OK the diff, so it matches the submission build | Your OK in #13 | 20:15 |
| V3 | **Vansh** | Demo run #2 feedback; decide the call policy (#17: keep calls as policy, or let the economics decide) and whether Anuj goes on the deck cover | Decisions posted in #13 | 11:00 |
| V5 | **Vansh** | Clear test decisions; record P1 segments (0:00–1:15, 4:15–5:00); stitch to ≤ 5:00, upload unlisted; deck → PDF; README links | Video link and deck PDF in the README | 18:30 |
| ✅ V7 | **P1 (Claude)** (done 12:55: EVALUATION regenerated + K6 OK, deck v14 + PDF, README 30 changes, AI_TOOLS; 20:00 = re-check only) | **Final pass (also slide 5: red-team 26/26 → 31/31, #27; slide 4: 19 → 20 DQ issue types + new diagram asset)** after 20:00 `run_all` (without `--update-deliverables`, so the 19:00 `answers.csv` stays):** regenerate `EVALUATION.md` on P1's build (K6, Kris OKs); slide 8: add the K8 dollar line (≈ +$160K expected payments per round), act-now 99.5% → value from the regenerated file (99.4% now); re-check fairness (5.1 now, deck says ≤ 5.5), README numbers and links; re-render the deck PDF | Every number in deck, README and video matches the final build | 20:30 |
| ✅ V6 | **P1 (Claude)** | Sync deck, README, diagram and video script to P1's build after #16 (8,877 → 8,883, 59,939 → 59,942, 46,226 → 46,235) | No number differs from P1's build | 12:00 |
| — | **All** | **19:00** final benchmark → **20:00** code freeze → final `run_all` + pytest → README links check → **submit by 20:30** (deadline 21:00) | Submitted | 20:30 |

**`main` is protected (4 Oct, 01:10):** no force pushes, no deletion, no direct pushes. Every change goes in through a PR, and only Vansh (code owner) can approve and merge it. Peer reviews still help: post your checks on the PR. The peer-merge rule in 🌙 below no longer applies.

**No new Claude calls before 19:00** (`--transcripts 0` stays the default). Post one line per finished task in #13.

## 📌 Final plan from P1 (3 Oct, 21:50 IST; done except the 4 Oct rows, now in ☀️ above)

**State:** everyone's work is merged into `main` (PRs #4, #6, #8, #10, #11, #12), verified by P1 on full data: 192 tests pass, benchmark dev 21/21, unseen rehearsal 21/21, all 5 app pages load. **No open issues.** Deck, README ("What changed": 24 rows) and video script have every number filled in.
**Deadline: 4 Oct, 21:00 IST** (commits after it don't count). Extra benchmark questions: **4 Oct, 19:00 IST**.

| Who | Task | When |
|---|---|---|
| **P1 Vansh** | Full `run_all` on `main` with the new stable `golden_id`s (running now) → restart the app → **demo run #2** (full click-through, `docs/pitch/video_script.md`) | 3 Oct, ~22:15 |
| **P2 Garv** | **Wire R5** now: Kris's merge added `gold.nba_recommendation.p_roll_forward`, so "which open cases are most likely to roll forward" can go live in Ask. Test after P1's run finishes (~22:15) | 3 Oct night |
| **P2 Garv** | Fix the broken French accent in one call quote (`"…depuis ao�t"`, case `CS-2026-899195`; raw notes are fine, so probably transcript reading/encoding). Found by Kris | 3 Oct night |
| **P3 Kris** | Small PR: drop the "golden_id differs between builds" note in `evaluation.py` (ids are stable now, commit `1fd561b`) and re-run `python -m ontrack.l4_nba.evaluation` on the new build | 3 Oct night |
| **P3 Kris** | Confirm or fix one voice-over line in `VIDEO_AGENT_CARD_SEGMENT.md`: "the salary deposits stopped" for `CS-2026-583749`. The card's reasons show reduced income, not salary | 3 Oct night |
| **P2 Garv** | Record the Ask segment (1:15–2:15) at 1080p: `python -m ontrack.l2_ask.warm_demo` first. Send the file (Drive link) to P1 | 4 Oct, by 14:00 |
| **P3 Kris** | Record the Agent card + evaluation segment (2:15–4:15) at 1080p. Search by `CS-2026-583749`. Send the file to P1 | 4 Oct, by 14:00 |
| **P1 Vansh** | Clear test decisions; record P1 segments (0:00–1:15, 4:15–5:00); stitch the video to ≤ 5:00; deck → PDF; README: video link, final check | 4 Oct, 14:00–18:30 |
| **P1 Vansh** (+ Garv on call) | **19:00: final benchmark** with the extra questions: `run_benchmark` on Vansh's laptop (runbook in `BENCHMARK_NOTES.md`), commit `benchmark/answers.csv` exactly as generated | 4 Oct, 19:00–19:45 |
| **All** | Code freeze 20:00; final `run_all` + submission by **20:30** (30 min buffer before 21:00) | 4 Oct |

### ✨ Polish tasks: make every part work perfectly (3 Oct night → 4 Oct 14:00)

Each one is done only when its "done when" holds on the full data. Post the result in issue #13.

| ID | Who | Task | Done when |
|---|---|---|---|
| ✅ G1 | **Garv** | **Answer stability:** run the benchmark 3× with a fresh LLM cache each time and diff the answers (BQ-014 showed answers can flip) | All data answers identical across the 3 runs; document / call answers keep the same facts and citations; any flip is fixed like BQ-014 |
| ✅ G2 | **Garv** | **Dry run of the 19:00 run:** a mock extra-questions file in the exact `benchmark_questions.csv` format (new ids, blank `metric_id`), run the way Vansh will run it (Claude Code CLI, `--workers 4`) | 0 errors, under 10 min for 35 + 15 questions, fallback written into the runbook (fewer workers, retry only failed ids) |
| ✅ G3 | **Garv** | **Ask page hardening:** try an empty question, "DROP TABLE cases", a 2,000-character question, French, emoji | No traceback ever; a clear message for each; the 5 example buttons answer in < 3 s after `warm_demo` |
| G4 | **Garv** | Record the Ask segment (1:15–2:15) and send it to Vansh | Every number on screen matches `VIDEO_ASK_SEGMENT.md`; 1080p, ≤ 60 s |
| ✅ K1 | **Kris** | **Repeatable training:** fixed seeds plus LightGBM `deterministic=True` and fixed `num_threads`, so a re-run gives the same numbers; then drop the golden_id note and regenerate `EVALUATION.md` on the new build (stable ids) | Two runs of `l4_nba.run` give identical AUCs and identical recommendations for all 96,000 cases |
| ✅ K2 | **Kris** | **Check the video facts:** confirm or fix "the salary deposits stopped" for `CS-2026-583749`, and every number in `VIDEO_AGENT_CARD_SEGMENT.md`, against the current build | Every claim traced to a query or table you can show |
| ✅ K3 | **Kris** | **Agent card on edge cases:** 5 random cases per action, plus no contacts, no bureau pull, French-speaking, cease, insolvency, deceased, dispute-only | All render with 3 reasons and no error; the page loads in < 3 s; accept / edit / reject each logged |
| K4 | **Kris** | Record the Agent card + evaluation segment (2:15–4:15) and send it to Vansh | Matches the checked script; 1080p, ≤ 2:00 |
| V1 | **Vansh (P1)** | Finish the full run with stable ids; add the accent issue to the DQ report as a coded check (19 issue types); update 18 → 19 in the deck, diagram and script | `run_all` all OK; DQ report regenerated, not hand-edited |
| V2 | **Vansh (P1)** | Test PR #14 (R5 + accent repair) on full data and merge it | R5 answers with SQL; demo quote reads "depuis août"; all tests pass |
| V3 | **Vansh (P1)** | Demo run #2, full click-through; time every page | Every page loads in < 3 s; nothing on screen contradicts the deck |
| V4 | **Vansh (P1)** | README "Submission" section at the top: links to every deliverable (architecture PDF/PNG, data contract, DQ report, `answers.csv`, deck PDF, video), plus a 3-command quick start for judges | Each link opens; a judge can run the system from the quick start alone |
| V5 | **Vansh (P1)** | Clear test decisions; record P1 segments; stitch the video (≤ 5:00); deck → PDF | Video uploaded unlisted, linked in the README |


### 🌙 P1 is offline for ~3 hours (Claude limit): work plan and merge rules until P1 is back

**Merge rule while P1 is away:** open a PR as usual. The *other* teammate reviews it and merges it (merge commit, never squash) only if **all** of these hold on their own machine:
1. `pytest tests/` passes in full;
2. `python scripts/run_all.py --skip-l1` ends all OK (no new LLM calls by default);
3. the PR touches only the author's folders;
4. `benchmark/answers.csv`, `README.md`, `TASKS.md` and `docs/` are untouched (P1 files).

Post the check results as a PR comment. Anything that needs P1 goes in issue #13; P1 reads it on return.
**Save Claude limits for tomorrow 19:00:** don't run `--transcripts N` or anything else that sends new calls to Claude.

**Garv, in order (~3 h):** G1 answer stability → G2 dry run of the 19:00 run → G3 Ask page bad inputs → **G5** R5 polish: leave bucket `180+` out of "roll forward", or call it charge-off risk (agree the wording with Kris on #13) → **review Kris's PRs** → G4 record your segment if your app is ready.

**Kris, in order (~3 h):** K1 repeatable training (seeds + `deterministic=True`) and regenerate `EVALUATION.md` → K2 check the video facts (incl. "salary deposits stopped") → K3 agent card on edge cases → **K5** `p_roll_forward` for `180+` cases (agree with Garv on G5) → **review Garv's PRs** → K4 record your segment.

**Done when** is in the ✨ table above. Post one line per finished task in #13: task id, result, PR link.


Rules unchanged: stay in your folders, PRs to `main`, never commit data / `.duckdb` / `.env`, no hand edits to `answers.csv`.

To see issues assigned to you: `gh issue list --assignee @me --repo VaNsH-IIIT/homies-ontrack`

## Phase 1 → **16:30 IST, 3 Oct** for P2 and P3 (first end-to-end test 16:30–17:30)

Goal: every layer runs at a basic level on real data, then we improve.
**P1's Layer 1 is done and on `main`:** run `python -m ontrack.l1_factory.bronze` once (~10 min) and `python -m ontrack.l1_factory.build` (~1 min) to get every `bronze.*` and `gold.*` table in your local DuckDB. Times in the "By" column below were set for a 9:30 start: shift yours by your start time, but aim to finish phase 1 by 16:30.
**When your phase-1 tasks are done, continue straight into your phase-2 tasks below; don't wait.**

### P1 · Vansh · Layer 1 (Data Product Factory) + integration

| ID | By | Task | Done when |
|---|---|---|---|
| ✅ P1-T1 | 11:00 | `src/ontrack/db.py` (`connect()` to `$ONTRACK_WORK_DIR/ontrack.duckdb`) and `python -m ontrack.l1_factory.bronze`: one `bronze.<table>` view per dataset table, following the release README conventions (NA codes, nulls, IDs as strings to keep leading zeros). **Push to `main` at once: it unblocks P2 and P3.** | `SELECT count(*)` works on every bronze view; row counts printed |
| ✅ P1-T2 | 11:30 | `scripts/make_sample.py`: a consistent 5% customer sample across all tables, for teammates with weak laptops (shared by Drive link, never git) | sample builds and the bronze views run on it |
| ✅ P1-T3 | 12:30 | Silver: standardise names, `*_dob_raw` → ISO dates, phones → E.164, postal → A1A 1A1; latest `snapshot_date` per account; current CRM rows only; `channel`/`channel_v2` drift; count every issue found as you go | silver tables built; issue counts recorded |
| ✅ P1-T4 | 13:30 | Identity resolution v1 (tier-1 bridges): `national_id_hash`, `duplicate_of_crm_id`, `collections_cases.account_ids`, `loan_accounts.pad_source_account` → `gold.customer_xref` with `match_confidence`; then **gold v0** of every `gold.*` table in the README interfaces | `python -m ontrack.l1_factory.build` creates all gold tables with the interface columns |
| ✅ P1-T5 | 14:00 | Data quality checks v1 → generated `docs/data_quality_report.md`: issue, records affected, how handled | report generated from code, not typed by hand |

### P2 · Garv · Layer 2 (Insight and NLP) + benchmark

The benchmark is **scored automatically** and counts towards the 30% technical score. Extra questions arrive at **19:00 on 4 Oct**, so the runner must answer a whole question file in **one command**, with no hand edits.

| ID | By | Task | Done when |
|---|---|---|---|
| ✅ P2-T1 | 11:00 | Study `data/benchmark_questions.csv`, `labels/benchmark_dev_answers.csv`, `labels/benchmark_answers_template.csv` and the "Benchmark questions" section of the release README. Write `src/ontrack/l2_ask/BENCHMARK_NOTES.md`: how many questions, types, tables each needs, which should be refused, answer format and tolerance. **Tell P1 if any question needs `promises_to_pay`.** | notes committed |
| ✅ P2-T2 | 11:45 | `python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv` writes a valid answers file for every question (placeholders allowed at first), plus `python -m ontrack.l2_ask.score_dev`, which scores against the dev answers | valid CSV in the template format; dev score printed |
| ✅ P2-T3 | 13:00 | Certified metrics from `metric_definitions` (templated SQL); NL-to-SQL with Claude for the rest; sqlglot validator (SELECT only, allow-listed tables and columns, `PROTECTED_COLUMNS` blocked, minimum group size 10, row cap); up to two repair tries. Runs on bronze now, gold later | dev questions answered with the SQL saved in `sql_or_sources` |
| ✅ P2-T4 | 13:30 | Refusal guard before SQL (protected attributes, PII lists, prohibited uses, non-collections questions) and after SQL (validator) | refusal accuracy on dev `should_refuse` questions printed |
| ✅ P2-T5 | 14:00 | Dev scoreboard in your PR: answer accuracy and refusal accuracy, plus the 3 worst failure types | numbers in the PR description |

### P3 · Kris · Layer 3 structured features + Layer 4 (NBA)

| ID | By | Task | Done when |
|---|---|---|---|
| P3-T1 | 11:00 | Study the release README, the dictionary for `collections_cases`, `contact_history`, `customers` (consent and hold flags), `hardship_programs` and the policy docs. Write `src/ontrack/l4_nba/DESIGN_NOTES.md`: action set, labels (self-cure in 30 days from `cure_flag`/`days_to_cure`; payment within 7 days of a contact; roll-forward from `dpd_at_day_30`), time-based train/validate/test split | notes committed |
| P3-T2 | 12:00 | `src/ontrack/l4_nba/policy_gate.py`: for each open case, the allowed actions and the blocked actions, each with a plain-English rule reason (consent per channel, cease, do-not-call, insolvency/deceased/third-party holds, dispute, contact cap, permitted hours, stat holidays, hardship eligibility) | unit tests cover each rule; runs on all open cases |
| P3-T3 | 13:00 | `src/ontrack/l3_features/structured/`: **one** function `build_case_features(con, as_of_date)` for both training and live scoring, point-in-time correct; writes `features.case_features`; outcome columns and `PROTECTED_COLUMNS` blocked | features built for a past date (training) and the snapshot date (scoring) with the same code |
| P3-T4 | 13:45 | Models v0 (LightGBM): self-cure and payment-within-7-days (or roll-forward), time split; compare with the existing `model_scores` and `nba_recommendation_last` | metrics printed (AUC, calibration) |
| P3-T5 | 14:00 | Ranker + explanations v0 → `gold.nba_recommendation` for open cases, with `reason_1..3` in plain English and `blocked_actions`; `l4.decision_log` table + `record_decision()` for accept/edit/reject | recommendations for all open cases; a sample of 5 printed with reasons |

## 16:30 → 17:30 · First end-to-end test (P1 runs it on the full data)

1. `l1_factory.build` → gold tables exist with interface columns.
2. `l2_ask.run_benchmark` on the released questions → dev score.
3. `l4_nba.run` → recommendations with reasons for open cases.
4. Each owner fixes what broke in their own part.

## Phase 2 · after your phase 1 → 22:00 IST, 3 Oct (start each as soon as you finish phase 1)

### P1 · Vansh
| ID | Task | Done when |
|---|---|---|
| ✅ P1-T2 | 5% dev sample (`scripts/make_sample.py`) | sample zip shared by Drive |
| ✅ P1-T6 | Probabilistic matching (Splink) for keys left unlinked by tiers 1–2; precision/recall measured on held-out tier-1 case-to-account links | fewer singletons; precision/recall in the DQ report |
| ✅ P1-T7 | Data contract YAML for `gold.c360_customer`, from `files/docs/data_contracts/` (DC-COLL-001) | `contracts/c360_customer.yaml` with owner, schema, quality rules, allowed uses, refresh |
| ✅ P1-T8 | Streamlit shell `src/ontrack/app/main.py` + page `1_C360.py` (customer lookup: golden record, linked keys with match confidence, accounts, timeline) | `streamlit run src/ontrack/app/main.py` shows pages 1–3 (2 and 3 load when P2/P3 add them) |
| ✅ P1-T9 | Final architecture diagram (PNG/PDF) in `docs/` | file in repo |

### P2 · Garv
| ID | Task | Done when |
|---|---|---|
| ✅ P2-T6 | Text signals with Claude: `hardship_signal`, `stated_delay_reason`, `stated_payday`, `dispute_mentioned`, each with a confidence and the exact evidence quote (+ `turn_index`). Score on `labels/agent_notes_labels_public_500.csv` and `labels/call_transcripts_labels_public_500.csv`; then run on notes/transcripts of open cases (batched, cached) → `features.text_signals` | precision/recall per signal printed; table written with the interface columns |
| ✅ P2-T7 | Cited search (RAG) over `reference_documents` (`files/docs/`) and agent notes, for document-type benchmark questions; answers cite `doc_id` / section or `note_id` | document questions in the dev set answered with citations |
| ✅ P2-T8 | Ask page `src/ontrack/app/pages/2_Ask.py`: question box, editable "understood as" tokens, answer table, **SQL shown**, clear refusal message | page works in the app |
| ✅ P2-T9 | Benchmark hardening: full released set (dev + test) → `benchmark/answers.csv` in one command; error analysis on dev; ready for the 19:00 extra questions on 4 Oct | answers file for all questions; dev score in PR |

### P3 · Kris
| ID | Task | Done when |
|---|---|---|
| P3-T6 | SHAP-based reasons: top 3 drivers per recommendation mapped to plain-English templates, plus a counterfactual line ("would change if …") | every recommendation has 3 readable reasons |
| P3-T7 | Hardship routing: combine structured signals (payroll delay, EI deposits, payment failures, case `hardship_flag`) with `features.text_signals` from P2 (when available) → `hardship_flag`, `needs_human_review`; hardship / vulnerability / dispute / complaint cases go to a human-only queue | counts of routed cases printed; routing reason stored |
| P3-T8 | Agent card page `src/ontrack/app/pages/3_Agent_Card.py`: pick a case → recommendation, reasons, blocked actions, hardship alert; accept / edit / reject with reason → `l4.decision_log` | an override recorded from the UI |
| P3-T9 | Evaluation for the deck: back-test vs `nba_recommendation_last` and `model_scores`; fairness check offline (recommended-action rates by protected group, used only to test) | numbers in `src/ontrack/l4_nba/EVALUATION.md` |

## Phase 3 · 4 Oct (planned at the 17:30 review)

| Owner | Planned |
|---|---|
| All | Polish, bug fixes on full data, README "how to run", deck (≤ 10 slides), 5-minute demo video, final benchmark run at 19:00 |

## Milestones

| By (IST) | Milestone |
|---|---|
| ✅ 3 Oct, 11:15 | Layer 1 (bronze → gold, DQ report, dev sample) on `main` |
| **3 Oct, 16:30** | **P2/P3 phase 1 done; first end-to-end test** |
| 3 Oct, 22:00 | Phase 2 core working on full data |
| 4 Oct, 12:00 | Benchmark runner stable in one command; demo app runs end to end |
| 4 Oct, 17:00 | Deliverables drafted: contract, DQ report, architecture, README, deck |
| 4 Oct, 19:00 | Extra benchmark questions released: run, check, commit |
| 4 Oct, 20:30 | Final commit; video and deck links submitted (30 min buffer) |
