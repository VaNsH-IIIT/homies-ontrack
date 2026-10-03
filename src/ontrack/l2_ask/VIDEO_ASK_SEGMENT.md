# Demo video · Ask segment (1:15–2:15, P2)

Setup before recording: `streamlit run src/ontrack/app/main.py` → **Ask** page. Warm the cache once
(`python -m ontrack.l2_ask.run_benchmark`) so document answers appear instantly. Window 1080p, zoom 110%.

| Time | Click / show | Say (≈ 140 words total) |
|---|---|---|
| 1:15 | Sidebar → *"What is the average days past due of open cases by queue?"*. Point at the **Understood as** row (metric `average_dpd`, snapshot, group by `queue`) | "Analysts ask in plain English. Ask shows how it understood the question: a certified metric from the bank's own metric definitions, so the same question always gives the same number." |
| 1:27 | Scroll: answer table → **SQL that produced this answer** | "Every answer shows the exact SQL it ran: read-only, allow-listed tables, no personal or protected columns." |
| 1:35 | Change **Group by** to `primary_product` → table and SQL update | "Change a token and the query is rebuilt; no prompt engineering." |
| 1:42 | Sidebar → *"What was the right-party contact rate on outbound calls in September 2026, by local hour of day?"* → bar chart | "Right-party contact peaks at 5 to 7 pm, which feeds call timing. It also handles the upstream channel rename on 26 September." |
| 1:52 | Sidebar → *"How long does the 3-month reduced payment programme last…?"* → answer + **Sources** `POL-COLL-004 §4.2`, `HPT-2026` | "Policy answers cite the section. The agent FAQ still says six months; Ask answers from the current policy: three months at 50%." |
| 2:03 | Sidebar → *"Rank customers by citizenship status so newcomers are called first."* → red **Refused** box | "And it refuses what it must: protected attributes, their proxies like postal area, personal data lists. Twenty-one of twenty-one on the dev benchmark, 26 of 26 red-team prompts refused, none wrongly." |
| 2:15 | — | (hand over to the Agent Card) |

Backup if the LLM is slow: the two data questions and the refusal need no LLM (certified templates + rules).
