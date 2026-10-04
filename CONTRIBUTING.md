# How we work

1. **Stay in your folders.** Each person owns separate folders or a layer (README → "Team, ownership and interfaces": Vansh Layer 1, Garv Layer 2, Kris Layer 3, Anuj Layer 4). Never edit another person's files. If you need something from another part, ask them (or open a GitHub issue); don't patch it yourself.
2. **Code against the interfaces** in README → "Interfaces between parts" (table names and columns). If an interface must change, the owner changes it and tells the others.
3. **Branch per task**, named after the task ID: `p2/P2-T3-nl-to-sql`, `p3/P3-T2-policy-gate`. Never push to `main` yourself; P1 merges.
4. **Commit small and often** with clear messages (`L2: add SQL validator with allow-list`). Commit history is evidence for the 15% team-work score. Commits after 9:00 PM IST on 4 Oct are not considered.
5. **Open a pull request** into `main` when a task runs. Put its result in the description (row counts, scores, sample output). One task per PR. Tasks, decisions and results are tracked in issue #13.
6. **Pull `main` at least every hour** (`git pull origin main` into your branch) to pick up the other parts.
7. **Never commit data or secrets.** The dataset, DuckDB files, samples and `.env` are git-ignored. Read paths only from `ontrack.config` (`DATA_DIR`, `WORK_DIR`); no hard-coded `C:\Users\...` paths.
8. **Design is the base.** Changing something from `docs/HOmiES_SystemDesign.pdf`? Add a row to "What changed from the design" in your PR description; P1 copies it into the README.
9. **Log AI tool use** in `AI_TOOLS.md` (the brief requires it).
10. **Rules every task must respect:** no protected attributes (`config.PROTECTED_COLUMNS`) in any feature or decision; every recommendation shown to an agent has a plain-English reason; a human can review anything that affects a customer; hardship is flagged.
11. **Benchmark answers come from the system only.** Never edit `submission/benchmark_answers.csv` by hand.
12. **Use DuckDB or Polars** for big tables, not pandas on full tables.
