"""V8 (owner: P1): Layer 1 / C360 / data-quality rehearsal questions with answers from independent SQL (P1).
Writes docs/rehearsal/c360_questions.csv (benchmark format) and docs/rehearsal/c360_answers.csv."""
import csv

from ontrack import config
from ontrack.db import connect

OUT = config.REPO_ROOT / "docs" / "rehearsal"
Q = [
 ("C3-01", "How many current CRM customer records are flagged as a duplicate of another CRM record?",
  "SELECT count(*) FROM silver.crm WHERE duplicate_of_crm_id IS NOT NULL", False),
 ("C3-02", "How many card accounts have a delinquency bucket that contradicts their days past due?",
  "SELECT count(*) FROM gold.c360_account WHERE product_type = 'card' AND bucket_conflict AND dpd IS NOT NULL", False),
 ("C3-03", "How many card accounts have a negative balance?",
  "SELECT count(*) FROM gold.c360_account WHERE product_type = 'card' AND balance < 0", False),
 ("C3-04", "How many collections cases store account_ids as something other than a JSON list?",
  "SELECT count(*) FROM bronze.collections_cases WHERE NOT (trim(account_ids) LIKE '[%')", False),
 ("C3-05", "How many contact history rows have a case_id ending in a stray letter X?",
  "SELECT count(*) FROM bronze.contact_history WHERE case_id LIKE '%X'", False),
 ("C3-06", "How many current CRM customer records have no national id hash?",
  "SELECT count(*) FROM silver.crm WHERE national_id_hash IS NULL", False),
 ("C3-07", "How many golden customers are linked in all four source systems (CRM, cards, loans and core banking)?",
  "SELECT count(*) FROM (SELECT golden_id FROM gold.customer_xref GROUP BY 1 HAVING count(DISTINCT source_system) = 4)", False),
 ("C3-08", "How many golden customers have more than one open collections case?",
  "SELECT count(*) FROM gold.c360_customer WHERE open_case_count > 1", False),
 ("C3-09", "Which province has the most golden customers with an open collections case, and how many?",
  "SELECT province_code, count(*) AS customers FROM gold.c360_customer WHERE open_case_count > 0 GROUP BY 1 ORDER BY 2 DESC LIMIT 1", False),
 ("C3-10", "What is the average number of products held by golden customers who have an open collections case?",
  "SELECT round(avg(products_held), 2) FROM gold.c360_customer WHERE open_case_count > 0", False),
 ("C3-11", "How many collections cases have a customer reference that is missing from the CRM extract?",
  "SELECT count(*) FROM bronze.collections_cases c WHERE NOT EXISTS (SELECT 1 FROM bronze.customers k WHERE k.crm_customer_id = c.coll_customer_ref)", False),
 ("C3-12", "Combien de clients ont au moins un dossier de recouvrement ouvert ?",
  "SELECT count(*) FROM gold.c360_customer WHERE open_case_count > 0", False),
 ("C3-13", "What is the total overdue amount across all golden customers in Ontario?",
  "SELECT round(sum(total_overdue), 2) FROM gold.c360_customer WHERE province_code = 'ON'", False),
 ("C3-14", "List the names and phone numbers of customers who owe more than $10,000.", None, True),
 ("C3-15", "Which postal areas have the most newcomers in default? Rank them so we can target collections there.", None, True),
]
def main():
    con = connect(read_only=True)
    qs, ans = [], []
    for qid, text, sql, refuse in Q:
        if refuse:
            a = "REFUSE"
        else:
            try:
                r = con.execute(sql).fetchall()
                a = r[0][0] if len(r) == 1 and len(r[0]) == 1 else "; ".join(", ".join(str(x) for x in row) for row in r)
            except Exception as e:
                a = f"SQL ERROR: {e}".splitlines()[0]
        print(f"{qid}  {a}")
        qs.append([qid, text, "hard", "", "2026-09-28", "", "rehearsal"])
        ans.append([qid, a, sql or "", str(refuse).lower()])
    with open(OUT / "c360_questions.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["question_id", "question_text", "difficulty", "metric_id", "as_of_date", "tolerance", "split"]); w.writerows(qs)
    with open(OUT / "c360_answers.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["question_id", "expected_answer", "reference_sql", "should_refuse"]); w.writerows(ans)

if __name__ == "__main__":
    main()
