# Demo video · Ask segment (1:15–2:15, P2)

Setup before recording: `streamlit run src/ontrack/app/main.py` → **Ask** page. Warm the cache with
`python -m ontrack.l2_ask.warm_demo` (asks these questions exactly as the page does, so each answers instantly).
Window 1080p, zoom 110%. Demo customer from `docs/pitch/video_script.md`: case `CS-2026-583749`.

| Time | Click / show | Say (≈ 150 words total) |
|---|---|---|
| 1:15 | Sidebar → *"What is the average days past due of open cases by queue?"*. Point at the **Understood as** row (metric `average_dpd`, snapshot, group by `queue`) | "Analysts ask in plain English. Ask shows how it understood the question: a certified metric from the bank's own metric definitions, so the same question always gives the same number." |
| 1:27 | Scroll: answer table → **SQL that produced this answer** | "Every answer shows the exact SQL it ran: read-only, allow-listed tables, no personal or protected columns." |
| 1:35 | Change **Group by** to `primary_product` → table and SQL update | "Change a token and the query is rebuilt; no prompt engineering." |
| 1:42 | Type *"Summarise the most recent recorded call on case CS-2026-583749: what did the customer say and agree to?"* → answer + **Sources** `transcript 4510675` | "It also reads calls. For our demo customer: their pay was cut in August, they can't pay the past-due amount, no promise was made, next step a hardship review, with the transcript cited." |
| 1:54 | Sidebar → *"How long does the 3-month reduced payment programme last…?"* → answer + **Sources** `POL-COLL-004 §4.2`, `HPT-2026` | "Policy answers cite the section. The agent FAQ still says six months; Ask answers from the current policy: three months at 50%." |
| 2:04 | Sidebar → *"Rank customers by citizenship status so newcomers are called first."* → red **Refused** box | "And it refuses what it must: protected attributes, proxies like postal area, personal data. Twenty-one of twenty-one on the dev benchmark, twenty-one of twenty-one on new questions we wrote, and twenty-six of twenty-six red-team prompts refused, none wrongly." |
| 2:15 | — | (hand over to the Agent Card) |

Backup if the LLM is slow: the certified question and the refusal need no LLM (templates + rules); the call and
policy answers come from the warmed cache.
