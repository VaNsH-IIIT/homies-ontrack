# AI tools used

Required by the brief: which AI tools we used and for what. Each teammate adds their own rows.

## AI tools used to build the system

| Tool | Used by | What for |
|---|---|---|
| Claude Code (Anthropic) | P1 Vansh | Design doc drafting and review; repo scaffold and team plan; Layer 1 code (bronze, silver, identity resolution incl. Splink, gold, data contract, DQ report); Streamlit shell and C360 page; architecture diagram; reviewing teammates' branches (found wrong column names, non-persisting decision buttons) |
| Claude Code (Anthropic) | P2 Garv | _to add_ |
| Claude Code (Anthropic) | P3 Kris | L3 structured feature engineering; L4 policy gate, LightGBM models, ranker with SHAP explanations, hardship routing, evaluation module, Agent Card Streamlit page; debugging column-name mismatches against real data |

## AI / ML inside the system

| Component | Technique | Where |
|---|---|---|
| Identity resolution, tier 3 | Splink (Fellegi-Sunter probabilistic record linkage, EM-trained, unsupervised) | `src/ontrack/l1_factory/probabilistic.py` |
| Layer 2 Ask | Claude (Anthropic API): NL-to-SQL over certified metrics, refusals, cited search | `src/ontrack/l2_ask/` (P2) |
| Layer 3 text features | Claude with a JSON schema: hardship signal, stated reason, stated payday, dispute, each with an evidence quote | `src/ontrack/l3_features/text/` (P2) |
| Layer 4 models | LightGBM + SHAP | `src/ontrack/l4_nba/` (P3) |

All data is synthetic, so sending it to an API is allowed by the brief. Protected attributes never reach any model or LLM call.
