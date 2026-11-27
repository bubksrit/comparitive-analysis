# CIC-IoT2023 exact global duplicate audit

- Run ID: `20261127T102218Z-b7c6e8c2`
- Status: `INCOMPLETE`
- Audit date: 2026-11-27
- Dataset root: `<LOCAL_CIC_IOT2023_CSV_ROOT>`
- CSV files: 309
- Expected rows: 46,776,700
- Rows scanned: None
- Candidate rows fully verified: 5786051
- Scratch available at preflight: 18,502,742,016 bytes
- Required free space: 10,737,418,240 bytes
- Estimated peak scratch: 7,184,901,120 bytes
- Audit scratch hard cap: 8,589,934,592 bytes
- Peak audit-owned scratch: 1,536,921,600 bytes

## Methodology

Pass 1 streams CSV records and writes only a 128-bit candidate fingerprint, file ID, and byte offset to a temporary SQLite index. Pass 2 considers only fingerprints occurring more than once, rereads those source records, and compares full canonical feature rows using disk-backed representative locators. No full feature row is persisted in the scratch database.

Offsets are captured from a binary stream immediately before csv.reader parses each logical record. Its lazy physical-line iterator preserves quoted fields, escaped quotes, CRLF and quoted multiline records. Candidate rereads seek to the captured byte offset and parse one complete logical CSV record.

BLAKE2b-128 is only a candidate fingerprint. Every candidate is reread and its complete 312-byte canonical row is compared against representative source rows. A fingerprint collision with different features creates separate representatives and is not counted as a duplicate.

Complete-row identity is the canonical 39-feature row plus folder-derived label. Feature-only representatives separately identify conflicting-label groups. Duplicate occurrences are records beyond the first for a feature/label group; within-file excess and additional represented files are reported separately.

## Results

No duplicate totals are reported as final because this run is incomplete.
- Rows processed before stopping: 46,776,700
- Stop reason: OperationalError: database is locked

## Limitations

- Labels are provenance labels derived from category folders, not independent ground truth.
- The audit counts duplicates and never removes or changes source records.
- No capture/session independence is inferred from file boundaries.
- The 128-byte-per-row scratch estimate is a planning estimate, not a measured database size; the 8 GiB cap and 2 GiB free-space reserve are enforced during the run.
- A pathological fingerprint bucket containing many distinct rows can make exact representative comparisons slow; disk use remains capped and the audit stops incomplete if its cap or free-space reserve is threatened.
