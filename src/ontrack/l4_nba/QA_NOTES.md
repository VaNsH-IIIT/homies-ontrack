# Layer 4: likely judge questions, short answers (P3, Kris)

Numbers are rounded so they hold on the submission build; exact values and methods are in `EVALUATION.md` (section in brackets).

**1. Why is the self-cure AUC 0.83 and not higher?**
Because it is honest. Our first version scored 0.96: it trained on cases that were already cured and read today's values into past rows. We rebuilt everything point-in-time (cases open at each monthly date, labels only after it) and dropped a column that only exists for still-open cases. 0.83 on an unseen month beats the bank's own model on the same cases (0.72), and removing the strongest feature still gives 0.83, so no single column carries the answer. On cases that later resolved it is weaker (about 0.59): the model is best at spotting cases that get stuck, which is what the ranker needs. (§1, §2)

**2. Why is the payment model only 0.58?**
In this data a payment is only recorded through a contact, and about a third of open cases have no contact in the next 7 days, so their label is 0 whatever the customer would do. We tried response history, link clicks, payday timing and simpler trees: nothing gained 0.03, so we kept it, and it only scales the ranker 0.5x-2x, never decides alone. (§1, K12 subsection)

**3. Are the probabilities calibrated?**
The order is right in every decile, but the level drifts: in this release the open book never resolves, so the share of cases curing within 30 days falls month by month (about 32%, 23%, 10%). A June calibrator over-predicts July by up to 8 points. That is why the agent card uses a calibrator fitted on the latest month with a complete outcome, and why "likely self-cure" is relative (3.5x the open book's rate), not a fixed 50%. (Calibration table in §1)

**4. Why do separated customers get more hardship referrals?**
Separated customers get hardship referrals about 61% of the time against about 47% for others, and the cause is upstream of the model: in the source data they carry the bank's hardship flag (49% vs 35%) and describe hardship in notes and calls (51% vs 38%) more often. Hardship goes to a person by policy. For decisions the model makes alone, every protected group stays within about 5.5 points, and the model's accuracy is similar for every group (AUC 0.80-0.85). Marital status is never an input; it is joined only offline for this check. (§5)

**5. Payment links beat calls on the numbers. Why still call anyone?**
Measured response: a link brings a payment within 7 days after about 12% of contacts, a call about 3%, at 240 times the cost of a text. So digital is the default. Calls are a deliberate policy for the cases with the most dollars at risk where contact has not worked, because a conversation is where hardship comes out (6% of calls vs none of the digital contacts) and arrangements are made. The agent card shows each channel's value, so the policy is visible, not hidden. Calls never exceed the 5,037 a day the bank can make. (§3, agent card "Why this channel")

**6. What does "about +$160K per round" mean, and what doesn't it mean?**
It means: for the same open cases on the same day, OnTrack's recommended contacts are expected to bring about $160K more in payments within 7 days than the bank's current recommendations. It is conservative: every payment is valued at the median ($72, the mean is about 2.6x higher), only cases OnTrack handles automatically count, and a bank recommendation the rules would block counts as nothing. It is not a forecast of annual savings, not a randomised uplift (response rates are observed), and a "round" is one recommended contact per case. (§2b)

**7. Why does 62% of the open book go to a person?**
Hardship first: the bank's flag, the customer's own words in notes and calls (nearly 9,000 cases the flag missed), or a payroll income shock. Holds (insolvency, deceased, third-party), cease requests, disputes, complaints and vulnerability also need a person by policy. Each case stores the reason; the split is in §4.

**8. Can agents actually cope with that queue?**
For new cases, yes. The hardship team works about 336 agent-hours a business day (`agent_shifts`), which is about 2,200 first contacts at the measured 7-minute handle time, or about 760 if a full assessment takes 20 minutes. About 490 new hardship referrals arrive each business day, so new cases are reached within a business day. Today's 46,000 referrals are a one-off backlog: about 27 business days to reach them all at the measured pace. They're worked highest dollars at risk first, so the first week reaches 18% of the cases, holding 57% of the hardship dollars at risk. The other human-only cases go to the existing specialist and stage teams. Those teams gain time because OnTrack recommends only the day's 5,037 calls, where the bank's engine recommends far more than capacity. Not modelled: overtime and repeat contacts. (§4b)

**9. How do you know nothing leaks or drifts between runs?**
Point-in-time tests on a synthetic database check the population, label windows and the as_of cut-off. Two runs from scratch give identical AUCs and identical recommendations for all 96,000 cases (fixed seeds, ordered inputs, deterministic tie-breaks). (DESIGN_NOTES)

**10. What would you do next?**
Learn "will they pay if contacted?" from randomised contacts (the champion / challenger cells), so channels get a true uplift; retrain from agents' accept / edit / reject decisions and outcomes; move scoring from daily batch to events.
