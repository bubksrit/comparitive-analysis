# CIC-IoT2023 exact global duplicate audit

- Status: `not_run_insufficient_scratch_space`
- Audit date: 2026-11-27
- Dataset root: `<LOCAL_CIC_IOT2023_CSV_ROOT>`
- CSV files in inventory: 309
- Expected rows from prior full audit: 46,776,700
- Scratch available: 13,648,265,216 bytes
- Scratch required (conservative estimate): 22,452,816,000 bytes
- Scratch shortfall: 8,804,550,784 bytes

## Methodology

CSV files are streamed in bounded pandas chunks into a temporary SQLite WITHOUT ROWID index. The index stores a vectorized 64-bit candidate fingerprint, the complete canonical 39-feature row, derived label, source file ID, and occurrence count. SQLite cache is capped and the temporary database is removed after reporting.

All 39 features are parsed numerically and encoded as little-endian float64. NaNs are normalized to one canonical NaN value; positive and negative zero are normalized to zero; infinities retain their sign. The immediate parent folder is mapped with the project multiclass label rule (Benign_Final to Benign).

A fingerprint match is only a candidate. Complete-row identity is keyed by the full canonical feature BLOB plus label ID and file ID in SQLite. Different canonical rows with the same fingerprint remain separate and are not counted as duplicates.

Complete-row identity includes all 39 canonical features and the folder-derived label. Duplicate occurrences are rows beyond the first within each full-row group. Within-file occurrences are excess copies within a source file; cross-file occurrences are additional represented source files. Conflicting-label groups share the full feature BLOB but have more than one derived label.

## Results

No CSV row contents were read. The audit stopped at preflight.
- Rows scanned: 0
- Exact duplicate occurrences: None
- Unique duplicate groups: None

## Limitations

- Folder-derived labels are provenance labels, not independently verified ground truth.
- Duplicate rows are counted, not removed or altered.
- No capture/session independence is inferred from file boundaries.
- The SQLite index stores full canonical rows; scratch use can approach the preflight upper bound.
- Scratch preflight failed; no CSV row contents were read and no temporary database was created.
