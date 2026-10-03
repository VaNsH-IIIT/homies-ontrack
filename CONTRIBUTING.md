# How we work

1. **Branch per task:** `p2/T7-nl-to-sql`, `p3/T12-hardship-extraction`. Never commit straight to `main` (P1 merges).
2. **Commit small and often**, with clear messages (`L2: add SQL validator with allow-list`). Commit history is evidence for the 15% team-work score, and commits after 9:00 PM IST on 4 Oct do not count.
3. **Pull request into `main`** when a task runs; P1 reviews and merges. Keep PRs to one task.
4. **Never commit data or secrets.** The dataset, DuckDB files and `.env` are git-ignored. Use `MAPLE_DATA_DIR` from `.env` for all paths; no hard-coded `C:\Users\...` paths.
5. **Design stays the base.** If you need to change something from `docs/HOmiES_SystemDesign.pdf`, add a row to "What changed from the design" in the README with the reason.
6. **Log AI tool use** in `AI_TOOLS.md` (the brief requires it): which tool, what for.
7. **Rules every task must respect:** no protected attributes in any feature or decision; every recommendation shown to an agent carries a plain-English reason; a human can review anything that affects a customer; hardship is flagged.
8. **Benchmark answers are produced by the system only.** Never edit `benchmark/*.csv` by hand.
