# OnTrack · Collections intelligence (Team HOmiES)

CIBC Collections Hackathon, build phase. **Deadline 9:00 PM IST, 4 Oct 2026.** Commits after that are not considered.

> **AI recommends. Rules constrain. Humans decide. Outcomes improve the next recommendation.**

Use case: **next best action (NBA)** for open collections cases, hardship-first, with a person in charge.
Our submitted design is the base: [`docs/HOmiES_SystemDesign.pdf`](docs/HOmiES_SystemDesign.pdf). Keep to it; log any change in [What changed from the design](#what-changed-from-the-design).

---

## 👉 Start here (every teammate)

Open Claude Code in an empty folder and paste **your** line:

| Who | Paste this into Claude Code |
|---|---|
| **P1 Vansh** | `Clone or pull https://github.com/VaNsH-IIIT/homies-ontrack. I am P1 (Vansh, lead). Read README.md, CONTRIBUTING.md and TASKS.md, then do the tasks assigned to P1, one branch per task, only inside P1's folders.` |
| **P2 Garv** | `Clone or pull https://github.com/VaNsH-IIIT/homies-ontrack. I am P2 (Garv). Read README.md, CONTRIBUTING.md and TASKS.md, then do the tasks assigned to P2, one branch per task, only inside P2's folders. Open a pull request for each task.` |
| **P3 Kris** | `Clone or pull https://github.com/VaNsH-IIIT/homies-ontrack. I am P3 (Kris). Read README.md, CONTRIBUTING.md and TASKS.md, then do the tasks assigned to P3, one branch per task, only inside P3's folders. Open a pull request for each task.` |

Then do the [Setup](#setup) once. Your tasks and their acceptance criteria are in [`TASKS.md`](TASKS.md).

---

## Team and ownership

Each person owns separate folders, so nobody edits anyone else's code. Shared interfaces are fixed in [Interfaces between parts](#interfaces-between-parts).

| | Name | GitHub | Owns (only this person edits these) |
|---|---|---|---|
| **P1** (lead) | Vansh Jaiswal | [@VaNsH-IIIT](https://github.com/VaNsH-IIIT) | **Layer 1** `src/ontrack/l1_factory/`, `src/ontrack/db.py`, `src/ontrack/config.py`, `contracts/`, `docs/`, `scripts/`, `src/ontrack/app/main.py`, `src/ontrack/app/pages/1_*.py`, `README.md`, `TASKS.md` |
| **P2** | Garv Pratap Singh | [@Gravity006](https://github.com/Gravity006) | **Layer 2** `src/ontrack/l2_ask/`, `benchmark/`, **Layer 3 text features** `src/ontrack/l3_features/text/`, `src/ontrack/app/pages/2_*.py` |
| **P3** | Kris Jain | [@KJKris05](https://github.com/KJKris05) | **Layer 3 structured features + feature store** `src/ontrack/l3_features/structured/`, **Layer 4** `src/ontrack/l4_nba/`, `src/ontrack/app/pages/3_*.py` |

Shared files: `requirements.txt` (append only; say what you added in your PR) and `AI_TOOLS.md` (add your rows).

---

## Setup

### 1. Prerequisites
- **Python 3.10+** and **git**.
- **About 12 GB free disk** for the dataset, on any drive, **outside the repo**. Example: `D:\maple_data`.
- 8 GB+ RAM. With less, use the **dev sample** (see [`TASKS.md`](TASKS.md), task P1-T2).
- An **Anthropic API key** for the LLM parts (P2 and P3).

### 2. Clone and install
```bash
git clone https://github.com/VaNsH-IIIT/homies-ontrack.git
cd homies-ontrack
python -m venv .venv
.venv\Scripts\activate            # Windows   |   source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
pip install -e .                  # makes `import ontrack` work everywhere
```

### 3. Configure
Copy `.env.example` to `.env` and fill it in:
```
MAPLE_DATA_DIR=D:/maple_data/maple_collections_release   # the unzipped release folder
ONTRACK_WORK_DIR=./data                                   # local DuckDB + samples (git-ignored)
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Get the data (**never commit it**; it stays outside git)
```bash
pip install -U huggingface_hub
hf download nuxsh/maple-collections-hackathon maple_collections_release.zip --repo-type dataset --local-dir D:/maple_data
cd D:/maple_data && unzip maple_collections_release.zip
```
Skip the voice zip: our design uses voice through transcripts only, with no acoustic features.

### 5. Check it works
```bash
python -c "from ontrack import config; print(config.DATA_DIR, config.DATA_DIR.exists())"
```
Should print your release folder and `True`.

---

## Where to look for what

| You need | Where |
|---|---|
| **Your tasks** for today and their acceptance criteria | [`TASKS.md`](TASKS.md) |
| How we work (branches, PRs, rules) | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| What we promised to build (our design, the base) | [`docs/HOmiES_SystemDesign.pdf`](docs/HOmiES_SystemDesign.pdf) |
| Build-phase brief (deliverables, judging, rules) | [`docs/brief/build_phase_instructions.pdf`](docs/brief/build_phase_instructions.pdf) |
| Design-phase brief | [`docs/brief/design_phase_problem_statement.pdf`](docs/brief/design_phase_problem_statement.pdf) |
| **Dataset README** (file conventions, nulls, NA codes, leading-zero IDs, loading code, customer key per system) | `$MAPLE_DATA_DIR/README.md`: **read this first** |
| Column reference | `$MAPLE_DATA_DIR/DATA_DICTIONARY.xlsx` |
| Benchmark questions (Layer 2) | `$MAPLE_DATA_DIR/data/benchmark_questions.csv` |
| Dev-split gold answers | `$MAPLE_DATA_DIR/labels/benchmark_dev_answers.csv` |
| Answer file format | `$MAPLE_DATA_DIR/labels/benchmark_answers_template.csv` |
| 500 public labels for notes and for transcripts (Layer 3 text features) | `$MAPLE_DATA_DIR/labels/` |
| Example data contract to start from (DC-COLL-001) | `$MAPLE_DATA_DIR/files/docs/data_contracts/` |
| Policy documents (RAG, hardship rules) | `$MAPLE_DATA_DIR/files/docs/` |
| Paths and settings in code | [`src/ontrack/config.py`](src/ontrack/config.py) (`DATA_DIR`, `WORK_DIR`, `PROTECTED_COLUMNS`) |
| AI tools we used (required in submission) | [`AI_TOOLS.md`](AI_TOOLS.md) |

---

## Interfaces between parts

Everyone codes against these names, so the three parts connect without waiting for each other. One local DuckDB file per person: `$ONTRACK_WORK_DIR/ontrack.duckdb`, opened with `ontrack.db.connect()` (P1).

| Schema.table | Built by | Read by | Minimum columns |
|---|---|---|---|
| `bronze.<table_name>` (one view per raw table, same names as the dataset) | P1 | all | as in the dataset |
| `gold.customer_xref` | P1 | P2, P3 | `golden_id, source_system, source_key, match_method, match_confidence` |
| `gold.c360_customer` | P1 | P2, P3 | `golden_id, primary_crm_customer_id, province_code, time_zone, preferred_language, consent_call, consent_sms, consent_email, consent_push, consent_autodialer, internal_do_not_call_flag, cease_communication_flag, insolvency_flag, deceased_flag, third_party_hold_flag, vulnerability_flag, products_held, total_exposure, total_overdue, max_dpd, open_case_count, match_confidence_min` |
| `gold.c360_account` | P1 | P2, P3 | `account_id, golden_id, product_type, balance, credit_limit, past_due_amount, dpd, dpd_bucket, account_status` |
| `gold.case_360` | P1 | P2, P3 | `case_id, golden_id, crm_customer_id` + cleaned `collections_cases` columns |
| `gold.contact_timeline` | P1 | P2, P3 | `golden_id, case_id, contact_id, contact_ts_utc, channel, outcome_code, rpc_flag, payment_taken_flag, note_id, transcript_id` |
| `features.text_signals` | P2 | P3 | `source_type ('note'/'transcript'), source_id, contact_id, case_id, crm_customer_id, event_ts, hardship_signal, hardship_confidence, evidence_quote, evidence_turn_index, stated_delay_reason, stated_payday, dispute_mentioned, model, prompt_version` |
| `features.case_features` | P3 | P3 | `case_id, golden_id, as_of_date` + feature columns, built by **one** function used for both training and live scoring |
| `gold.nba_recommendation` | P3 | P2 (Ask can query it) | `case_id, golden_id, as_of_ts, action, channel, time_window, score, reason_1, reason_2, reason_3, blocked_actions, hardship_flag, needs_human_review, model_version` |
| `l4.decision_log` | P3 | P1 (demo) | `decision_id, case_id, agent_id, recommended_action, agent_action ('accept'/'edit'/'reject'), final_action, reason_code, note, ts` |

**Until `gold.*` exists,** work from the `bronze.*` views. Same column names, so switching over is a one-line change.
**Design rule:** `promises_to_pay` is out of scope in our design (30 tables in scope). If a benchmark question needs it, P2 raises it with P1, who decides.
**Never** read a column in `config.PROTECTED_COLUMNS` in features or decisions.

---

## Repository layout

```
src/ontrack/
  config.py          paths and settings (P1)
  db.py              DuckDB connection + bronze views (P1)
  l1_factory/        Layer 1: raw -> silver -> gold C360, ID matching, data quality (P1)
  l2_ask/            Layer 2: questions -> SQL or sources, refusals, benchmark runner (P2)
  l3_features/
    text/            LLM text signals from notes and transcripts (P2)
    structured/      structured features + feature store definitions (P3)
  l4_nba/            Layer 4: policy gate, models, ranking, explanations, decision log (P3)
  app/               Streamlit demo: main.py + pages/1_* (P1), 2_* (P2), 3_* (P3)
contracts/           data contract YAML for gold C360 (P1)
benchmark/           benchmark answers CSV, generated by the system only (P2)
docs/                design PDF, briefs, architecture, data quality report (P1)
scripts/             data download and runners (P1)
data/                local only, git-ignored
```

---

## How to run

_Filled in as the layers land. Target: one command per step._

| Step | Command | Owner |
|---|---|---|
| Build bronze views | `python -m ontrack.l1_factory.bronze` | P1 |
| Build silver + gold C360 | `python -m ontrack.l1_factory.build` | P1 |
| Answer benchmark questions | `python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv` | P2 |
| Extract text signals | `python -m ontrack.l3_features.text.extract` | P2 |
| Build features, train, recommend | `python -m ontrack.l4_nba.run` | P3 |
| Demo app | `streamlit run src/ontrack/app/main.py` | P1 |

---

## What changed from the design

_Required by the brief. Add a row for every change and why._

| Change | Why | Who |
|---|---|---|
| | | |

## AI tools used

_Required by the brief. See [`AI_TOOLS.md`](AI_TOOLS.md)._
