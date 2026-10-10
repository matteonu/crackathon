# Production seed

**Intentionally empty.** `main` runs with a clean database: schema only, no rows, so the live
app starts with nothing in it and every visitor gets an empty workspace of their own.

Put a `NN_<table>.json` file here only for rows that every real user should see — a real
course catalog, say. The example courses and the demo users live in `../seed_demo/`, which
dev mode overlays on top of this directory (`SEED_DIRS`). Nothing in `seed_demo/` ever
reaches production.
