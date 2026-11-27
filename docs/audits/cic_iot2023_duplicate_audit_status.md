# CIC-IoT2023 duplicate audit status

**Status date:** 2026-11-27 <br>
**Raw dataset:** `<LOCAL_CIC_IOT2023_CSV_ROOT>` <br>
**Source rows:** 46,776,700 across 309 CSV files

## Global audit

The latest exact global run is
[`20261127T102218Z-b7c6e8c2`](cic_iot2023_duplicate_audit_20261127T102218Z-b7c6e8c2/report.md).
It scanned all 46,776,700 rows, verified 5,786,051 candidate rows, and performed 5,390,828
full feature comparisons. It stopped with `OperationalError: database is locked` while exact
candidate verification was in progress. The audit-owned temporary index was cleaned up; no
resumable checkpoint remains. Its status is **INCOMPLETE**, and no global duplicate total may
be reported.

The earlier reports in this directory are historical attempts. The preflight-only summary
[`cic_iot2023_duplicate_audit.md`](cic_iot2023_duplicate_audit.md) predates the full scan and
is not the current status.

## Efficient valid scope for development

The prepared 160,578-row sample was audited exactly, with counts scoped to that sample:

- 2,524 exact full-record duplicate occurrences retained.
- 3,794 identical eligible feature-vector duplicate occurrences retained, including vectors
  with different folder-derived labels.
- No rows removed.
- The data split groups identical eligible feature vectors together and reports no overlap.

These sample counts do not estimate or imply global raw-dataset duplicate totals. See the
[sample audit](cic_iot2023_sample_duplicate_audit_8f5fa66e8616.md) and the split audit at
`outputs/cic-iot2023-development/audit.json`.
