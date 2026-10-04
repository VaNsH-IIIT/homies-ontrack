# AI tools used

Required by the brief: which AI tools we used and for what. Each teammate adds their own rows.

## AI tools used to build the system

| Tool | Used by | What for |
|---|---|---|
| Claude Code (Anthropic) | P1 Vansh (Layer 1, build lead) | Build plan from the design; Layer 1 code: bronze, silver, identity resolution (exact rules, Splink, conflict guard), gold Customer 360; executable data contract and data quality report; C360 and Match review pages with the steward feedback loop; architecture diagram; verified every pull request on the full data before merging; pre-submission checks |
| Claude Code (Anthropic) | P2 Garv (Layer 2) | Layer 2 Ask: benchmark runner and dev scorer, certified-metric SQL templates, sqlglot SQL guard, scope guard and refusals, Claude agent for guarded SQL and cited answers, BM25 search, Ask page; Layer 3 text signals: note and call models, Claude extraction with verified quotes, evaluation on the public labels; answer-stability runs; 19:00 runner hardening and backup runner |
| Claude Code (Anthropic) | P3 Kris (Layer 3) | Layer 3 feature store: one point-in-time `build_case_features` for training and live scoring, label-leakage fix; Layer 4 engine code: policy gate, LightGBM self-cure / payment / roll-forward models, capacity-aware ranker, SHAP-based reasons, Agent card page; repeatable training (identical results across runs); tests for every rule |
| Claude Code (Anthropic) | P4 Anuj (Layer 4, design lead) | Designed the four-layer architecture and the interfaces between layers in the design phase; Layer 4 hardship routing (who goes to the human-only queue, and why) and hardship-team capacity against real shift data; evaluation and business case with P3: back-test against the bank's own model, fairness check, dollar value; the feedback loop that turns every decision and its outcome into labels for retraining; policy gate rules checked against the policy documents; live-question and red-team sets with P2; Layer 4 judge Q&A |

## How we worked with AI (build phase, 3–4 Oct)

- **Four people, three machines.** Anuj worked through the team's Claude Code sessions on all three machines. He tested and rehearsed each layer and checked Layer 4 against the policy documents, so his work appears under the other members' accounts.
- **One Claude Code session per owner, one lead session.** Each teammate's session worked only in its owner's folders, through branches and pull requests. P1's session acted as lead: it assigned tasks in issue #13, verified every PR on the full data, and merged with merge commits. `main` is protected; only P1 merges.
- **Verification, not trust.** Before merging, the lead session re-ran the tests and the affected pipeline steps, and compared outputs. For example, all 96,000 recommendations were compared column by column to prove that a refactor changed nothing (#34). The benchmark answers file is only ever written by `run_benchmark`, never edited by hand.
- **Sessions reviewed each other.** On the night of 3–4 Oct, while the humans slept, the three sessions cross-reviewed each other's work and found real issues. Examples: non-standard province codes in Layer 1 (DQ issue 20, found by P2's rehearsal), a check that misread reordered question files, a 19:00 path that could have dropped the 35 released answers, and a test that needed the dataset. Every finding was fixed with a test. Results are logged in issue #13.
- **Claude usage was budgeted.** The pipeline runs with no LLM calls by default (`--transcripts 0`; cached results reused). Rehearsals ran on teammates' own allowances, so the final benchmark run had headroom.
- **People decided.** Design choices (calls as a policy, what counts as hardship, what is refused), ownership and every merge were human decisions or human-delegated, logged in issue #13 and the README "What changed" table.

## AI / ML inside the system

| Component | Technique | Where |
|---|---|---|
| Identity resolution, tier 3 | Splink (Fellegi-Sunter probabilistic record linkage, EM-trained, unsupervised) | `src/ontrack/l1_factory/probabilistic.py` |
| Layer 2 Ask | Rules + certified-metric SQL templates first (no LLM); then a Claude agent (Anthropic API, or the Claude Code CLI as fallback) writes guarded SQL and cited document / call answers; BM25 (DuckDB full-text) search over policy sections and notes | `src/ontrack/l2_ask/` (P2) |
| Layer 3 text features | Character n-gram logistic-regression models trained on the 500 public labels (notes and calls; every note and call of open cases), plus Claude with a JSON schema on calls (quote verified in its turn): hardship signal, stated reason, stated payday, dispute, each with evidence | `src/ontrack/l3_features/text/` (P2) |
| Layer 4 models | LightGBM + SHAP; back-test and fairness check | `src/ontrack/l4_nba/` (P3; hardship routing, capacity and evaluation P4) |

All data is synthetic, so sending it to an API is allowed by the brief. Protected attributes never reach any model or LLM call.
