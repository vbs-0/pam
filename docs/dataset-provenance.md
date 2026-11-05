# Dataset provenance and verification

PAM's data is **synthetic only**. Every record is produced by this repository's generator from a fixed seed
(`20261022`). No real person, account, merchant, bank or transaction data was used, copied or scraped, so there is no
external source, licence or consent to record. The generator and the files it writes are the whole provenance.

## What is committed, and what is regenerated

| Scale | Where | Committed |
|---|---|---|
| Starter: 50 households, 25,000 transactions | `data/starter/` | everything: CSV (`inputs/`, `ground_truth/`), JSON, `seed.sql`, `manifest.json`, `provenance.json` |
| Full: 1,000 households, 500,000 transactions | `data/full/` (about 500 MB) | **not committed**; its manifest, provenance record, validation, evaluation and reproducibility reports are in `reports/full/` |

The full dataset is regenerated exactly with one command, and the committed manifest tells you whether you got the
same bytes:

```bash
cd backend
uv run python -m app.cli generate --scale full && uv run python -m app.cli export --scale full
sha256sum ../data/full/manifest.json      # must equal the value in docs/manifest-hashes.sha256
uv run python -m app.cli validate-dataset --scale full
```

## Files that describe a dataset

| File | Content | Deterministic |
|---|---|---|
| `manifest.json` | seed, parameters, and for every CSV its row count and SHA-256 | yes: identical on every run |
| `provenance.json` | `synthetic_only: true`, generator source hash, git commit and whether the generator tree was clean, Python version, platform, dependency-lock hash, command line, the manifest's SHA-256 and the row count and SHA-256 of every JSON file and of `seed.sql` | no: it records the machine and commit, so it is excluded from the reproducibility comparison |

## How tampering would be noticed

A manifest sits next to the files it describes, so on its own it proves little: someone could edit a CSV and the
manifest together. The checks below make that visible from outside the data folder.

1. **Published manifest hashes.** [`manifest-hashes.sha256`](manifest-hashes.sha256) lists the SHA-256 of the starter and
   the full manifest. CI runs `sha256sum -c` on it, so editing a manifest changes a hash that is in a separate file
   and in git history.
2. **The committed starter equals the generator's output.** CI regenerates the starter dataset, exports it, and `diff`s
   every CSV, JSON file, `seed.sql` and the manifest against what is committed. Any hand edit fails the build.
3. **Reproducibility covers every artifact.** `repro` generates and exports twice in fresh interpreters with different
   `PYTHONHASHSEED` values and compares the CSV manifest and the checksum of every JSON file and of `seed.sql`
   (`reports/starter/reproducibility.json`, `reports/full/reproducibility.json`).
4. **Validation cross-checks the files.** `validate-dataset` rejects missing or unexpected files, JSON files or `seed.sql`
   whose row counts differ from the CSVs, and any file that no longer matches `provenance.json`, besides the key, join,
   enum, date, arithmetic and lifecycle checks. It also enforces rules a database `CHECK` cannot express: exactly one
   primary holder per account, holders joining inside the account's life, contiguous monthly balance rows that chain,
   credit limits only on cards, and ordered effective dates.

**Rule for anyone touching the data:** these files are generated artifacts. Fix the generator and regenerate; never edit
a file by hand.

## What "reproducible" means here

The checksums are identical across runs, across `PYTHONHASHSEED` values and across operating systems for the locked
environment: Python 3.12 and the exact versions in `backend/uv.lock`. It is not claimed for other Python versions or
dependency versions, which could change number formatting or ordering.
