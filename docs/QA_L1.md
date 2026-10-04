# Layer 1: likely judge questions, short answers (P1, Vansh)

Numbers from the submission build (4 Oct). Sources: [`docs/data_quality_report.md`](data_quality_report.md), [`contracts/c360_customer.yaml`](../contracts/c360_customer.yaml), the Home page.

**1. How do you know the customer matching is right?**
We tested it blind. 5,000 source keys whose owner we already knew from case-to-account links were hidden and matched again: **precision 99.8%, recall 99.4%**. Matching runs in tiers. Exact bridges come first (case accounts, PAD source accounts, national id, CRM's own duplicate flag), then exact name + date of birth + postal code or phone, then Splink (probabilistic record linkage) for what's left. Every link stores its method and confidence (contract rule Q2).

**2. Why not merge more aggressively?**
A wrong merge is worse than a missed one: an agent would see someone else's debts. So:
- a conflict guard never joins two people whose dates of birth differ (it refuses over 1,000 such links per build);
- matches between 0.80 and 0.95 probability (**1,924**) are never merged automatically. A data steward approves or rejects them on the Match review page, with masked evidence, and the next build applies the decision.
- Contract rule Q6 checks that no golden customer holds two dates of birth.

**3. What did you find wrong in the data, and what did you do about it?**
**20 issue types**, each counted by code and handled. They're in the generated DQ report, never typed by hand. Examples:
- dates of birth in 7 formats;
- card names in 3 formats;
- masked phone digits;
- card buckets contradicting days past due (24,205);
- `contact_history.channel` moved to `channel_v2` by a release;
- 4,636 French notes with lost accents (repaired by P2);
- province written as "Ont.", "B.C." or "Quebec" (10,657 records). A teammate's question rehearsal found that one this morning, and it's fixed at the source.

**4. What is the data contract, and what happens when it fails?**
`DC-COLL-C360-001` has 8 executable rules: unique golden id, link confidence, no orphan cases, consent flags never null, valid amounts, no cross-birthdate merge, no protected or PII column in any gold table, freshness under 24 hours. They run on every build, and **a failure stops the build** after the DQ report is written.

**5. How do you keep personal data and protected attributes out?**
- Names, dates of birth and contact details are used for matching in silver only and never reach gold, the app, features or LLM calls.
- The 12 protected attributes plus age are blocked everywhere downstream (Q7 checks every gold table).
- Stewards see masked evidence (initials, postal area only).

**6. Is the golden id stable? Can I link to it tomorrow?**
Yes. It's a hash of the person's anchor key (their smallest CRM key, otherwise their smallest source key), so rebuilding gives the same id. The demo customer is always `G-B8B48059904D178B`.

**7. Why DuckDB and not dbt, Dagster or Spark?**
For a 36-hour build, plain SQL in Python modules gave one command that builds everything in about 10 minutes for 1 million people. It's the same layered design (bronze → silver → gold, contract, DQ report). The production path is the one in our design document: the same SQL on the bank's warehouse, with an orchestrator and a catalog.

**8. How big is it?**
- 1,000,000 people and 1,020,000 CRM records become **1,015,637 golden customers**;
- 3,067,649 source keys linked;
- 1,844,500 accounts;
- 96,000 open cases.

**9. Is everything repeatable?**
Customer counts, links and every number we publish are the same on every build. One honest caveat: Splink's model training isn't bit-for-bit repeatable, so the number of links the conflict guard refuses moves slightly between builds (about 1,080–1,140). We quote it as "over 1,000".

**10. What would you do next?**
Learn match thresholds from steward decisions; keep history per snapshot in gold (today it holds one current row per customer); publish the contract to the bank's data catalog.
