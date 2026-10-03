# AI tools used

Required by the brief: which AI tools we used and for what. Each teammate adds their own rows.

## AI tools used to build the system

| Tool | Used by | What for |
|---|---|---|
| Claude Code (Anthropic) | P1 Vansh | Design doc drafting and review; repo scaffold and team plan; Layer 1 code (bronze, silver, identity resolution incl. Splink, gold, data contract, DQ report); Streamlit shell and C360 page; architecture diagram; reviewing teammates' branches (found wrong column names, non-persisting decision buttons) |
| Claude Code (Anthropic) | P2 Garv | Read the brief, design and dataset; benchmark analysis (BENCHMARK_NOTES.md); Layer 2 code: runner and dev scorer, sqlglot SQL guard, certified-metric SQL templates and "understood as" parser, scope guard rules and red-team set, Claude tool agent for NL-to-SQL and cited answers; all code reviewed and tested against dev gold answers |
| Claude Code (Anthropic) | P3 Kris | Layer 3 structured features (point-in-time `build_case_features`) and Layer 4: policy gate, LightGBM self-cure / payment models, label-leakage fix, capacity-aware ranker, SHAP-based business reasons, hardship routing, evaluation (back-test, fairness), Agent card page and tests; code reviewed and run on the full data |

## AI / ML inside the system

| Component | Technique | Where |
|---|---|---|
| Identity resolution, tier 3 | Splink (Fellegi-Sunter probabilistic record linkage, EM-trained, unsupervised) | `src/ontrack/l1_factory/probabilistic.py` |
| Layer 2 Ask | Claude (Anthropic API): NL-to-SQL over certified metrics, refusals, cited search | `src/ontrack/l2_ask/` (P2) |
| Layer 3 text features | Claude with a JSON schema: hardship signal, stated reason, stated payday, dispute, each with an evidence quote | `src/ontrack/l3_features/text/` (P2) |
| Layer 4 models | LightGBM + SHAP | `src/ontrack/l4_nba/` (P3) |

All data is synthetic, so sending it to an API is allowed by the brief. Protected attributes never reach any model or LLM call.
