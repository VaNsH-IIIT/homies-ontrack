# AI tools used

Required by the brief: which AI tools we used and for what. Each teammate adds their own rows.

## AI tools used to build the system

| Tool | Used by | What for |
|---|---|---|
| Claude Code (Anthropic) | P1 Vansh | Design doc drafting and review; repo scaffold and team plan; Layer 1 code (bronze, silver, identity resolution incl. Splink, gold, data contract, DQ report); Streamlit shell and C360 page; architecture diagram; reviewing teammates' branches (found wrong column names, non-persisting decision buttons) |
| Claude Code (Anthropic) | P2 Garv | Read the brief, design and dataset; benchmark analysis (BENCHMARK_NOTES.md); Layer 2 code: runner and dev scorer, sqlglot SQL guard, certified-metric SQL templates and "understood as" parser, scope guard rules and red-team set, Claude agent for NL-to-SQL and cited answers, BM25 cited search, Ask page; Layer 3 text code: notes and call models, Claude extraction with verified quotes, evaluation on the public labels; unseen rehearsals (21 benchmark-style, 29 hard, 8 Layer 1, and P1's 15 C360) with answers from independent SQL, and a hand-check of the 14 test answers; answer-stability runs (3 fresh runs, data conventions fixed where answers wandered); prompt-injection hardening and red-team; 19:00 runner hardening (any file shape, duplicate and blank ids, `--retry-failed`) and a backup runner that never drops the released 35; roll-forward and charge-off lists over P3's scores; French accent repair for 4,636 notes; 113 pytest tests (`tests/test_l2_*`); peer reviews of P3's PRs; PR descriptions and the team status report. All code reviewed and tested against the dev gold answers and hand-written SQL |
| Claude Code (Anthropic) | P3 Kris | Layer 3 structured features (point-in-time `build_case_features`) and Layer 4: policy gate, LightGBM self-cure / payment models, label-leakage fix, capacity-aware ranker, SHAP-based business reasons, hardship routing, evaluation (back-test, fairness), Agent card page and tests; code reviewed and run on the full data |

## How we worked with AI (build phase, 3–4 Oct)

- **One Claude Code session per owner, one lead session.** Each teammate's session worked only in its owner's folders, through branches and pull requests. P1's session acted as lead: it assigned tasks in `TASKS.md` and issue #13, verified every PR on the full data, and merged with merge commits. `main` is protected; only P1 merges.
- **Verification, not trust.** Before merging, the lead session re-ran the tests and the affected pipeline steps, and compared outputs. For example, all 96,000 recommendations were compared column by column to prove that a refactor changed nothing (#34, K19). The benchmark answers file is only ever written by `run_benchmark`, never edited by hand.
- **Sessions reviewed each other.** On the night of 3–4 Oct, while the humans slept, the three sessions cross-reviewed each other's work and found real issues. Examples: non-standard province codes in Layer 1 (DQ issue 20, found by P2's rehearsal), a check that misread reordered question files, a 19:00 path that could have dropped the 35 released answers, and a test that needed the dataset. Every finding was fixed with a test. Results are logged in issue #13.
- **Claude usage was budgeted.** The pipeline runs with no LLM calls by default (`--transcripts 0`; cached results reused). Rehearsals ran on teammates' own allowances, so the final benchmark run had headroom.
- **People decided.** Design choices (calls as a policy, what counts as hardship, what is refused), ownership and every merge were human decisions or human-delegated, logged in issue #13 and the README "What changed" table.

## AI / ML inside the system

| Component | Technique | Where |
|---|---|---|
| Identity resolution, tier 3 | Splink (Fellegi-Sunter probabilistic record linkage, EM-trained, unsupervised) | `src/ontrack/l1_factory/probabilistic.py` |
| Layer 2 Ask | Rules + certified-metric SQL templates first (no LLM); then a Claude agent (Anthropic API, or the Claude Code CLI as fallback) writes guarded SQL and cited document / call answers; BM25 (DuckDB full-text) search over policy sections and notes | `src/ontrack/l2_ask/` (P2) |
| Layer 3 text features | Character n-gram logistic-regression models trained on the 500 public labels (notes and calls; every note and call of open cases), plus Claude with a JSON schema on calls (quote verified in its turn): hardship signal, stated reason, stated payday, dispute, each with evidence | `src/ontrack/l3_features/text/` (P2) |
| Layer 4 models | LightGBM + SHAP | `src/ontrack/l4_nba/` (P3) |

All data is synthetic, so sending it to an API is allowed by the brief. Protected attributes never reach any model or LLM call.
