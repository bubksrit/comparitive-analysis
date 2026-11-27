# CICIoT2023 provenance and ground-truth audit

**Audit date:** 2026-11-27 <br>
**Scope:** repository records, active dataset config, loader/preparation code, saved local audit/manifests, the local `README_CSV.pdf`, official CIC pages, and the cited paper. No raw CSV was changed and no dataset was downloaded.

## Findings at a glance

The official CICIoT2023 dataset and its intended use for IoT intrusion classification are verified from the CIC page and its 2023 paper. The local data are structurally compatible with a 34-way intrusion-label task in the limited sense that a prior full local audit found 309 CSVs, 34 directories, 39 numeric columns per CSV and 46,776,700 rows, and the directory names resemble the 33 attack types plus benign traffic described in the paper.

However, **the identity of these exact local files as an unmodified official CIC download is not verified**. The local source package's own `README_CSV.pdf` conflicts with the data actually audited: it describes combined/shuffled CSV data with a `label` feature, while the local files were audited as separate per-category files with 39 feature columns and no label column. The 34 folder labels are therefore locally derived proxies, not independently checked row-level ground truth. In particular, the mapping `Benign_Final` → `Benign` is semantically plausible but not established by the official source materials found in this audit.

Treat existing model results as **preliminary exploratory intrusion-classification results on a locally folder-labelled, class-capped sample**. Do not present them as verified-label benchmark results, official-source replication, load-balancing performance, or faculty-approved dataset results.

## 1. Verified source identity and publication

- The official source page is the [Canadian Institute for Cybersecurity (CIC), University of New Brunswick, “CIC IoT dataset 2023”](https://www.unb.ca/cic/datasets/iotdataset-2023.html). It describes 33 attacks across seven categories, a 105-device IoT topology, and CSV features extracted from captured traffic. Its download control leads to the [CIC dataset download form](https://cicresearch.ca/IOTDataset/CIC_IOT_Dataset2023/); the page requires a form and is not a directly versioned archive URL.
- The associated publication is E. C. P. Neto, S. Dadkhah, R. Ferreira, A. Zohourian, R. Lu, and A. A. Ghorbani, “CICIoT2023: A Real-Time Dataset and Benchmark for Large-Scale Attacks in IoT Environment,” *Sensors*, 23(13), 5941 (published 26 June 2023), [doi:10.3390/s23135941](https://doi.org/10.3390/s23135941). It describes packet-capture generation and labeling, feature extraction into CSV, and evaluates binary, grouped 8-class, and 34-class intrusion classification.
- The publication is CC BY 4.0 as an article. That license statement should not be treated as the dataset's license. CIC's [dataset FAQ](https://www.unb.ca/cic/datasets/) says datasets may be redistributed, republished, and mirrored if the dataset and listed paper are cited, while also acknowledging that a licensing note may be absent. Record this as the publisher's reuse guidance, not as a named standard license for the local files.
- The active project config `backend/config/cic-iot2023-final.json` names the CIC page and release year, but has `retrieval_date: null`. It does not identify the downloaded form/session, archive or mirror, archive checksum, or a source-side checksum. Consequently the official download route and publication are known, but the path by which these particular local files were obtained is not.

## 2. Local structure and schema comparison

The saved local audit `docs/audits/cic_iot2023_audit.json` records 34 top-level directories, 309 CSV files, 46,776,700 rows, 8,943,771,319 bytes, zero schema mismatches and 39 expected numeric feature columns. It records local file paths, sizes and SHA-256 values. The loader `backend/app/features/iot_loader.py` checks this 39-feature contract; `iot_preparation.py` derives a label from the immediate parent directory and writes the sample manifest. These checks establish internal consistency of the audited local files, not their origin.

The official CIC page's feature summary also lists fields absent from the local 39-feature contract, including `flow_duration`, `Duration`, `Srate`, `Drate`, `urg_count`, `Magnitue`, `Radius`, `Covariance`, and `Weight`. The local README creates a second material contradiction: the supplied local source-package README (`README_CSV.pdf`) says the CSV folder contains 309 CSVs “combined and shuffled” and that attacks are identified by a `label` feature. By contrast, the local audit and loader treat the files as category-separated, with no label field in each raw CSV. The local tree is internally schema-consistent but **does not match the official page's published feature summary or the local README's described CSV organization/schema**. No source archive was available in the repository for a byte-for-byte or archive-manifest comparison.

The directory and file totals match the README's stated count of 309 CSVs, and the local 34 folders are compatible in cardinality with the paper's 33 attacks plus benign traffic. These are consistency clues only. They do not identify the exact release variant or establish that the contents are unmodified publisher files.

## 3. Label and 34-class assessment

The paper supports an intended 34-class classification framing: benign traffic plus 33 individual attacks. It also describes labeling traffic by attack scenario during collection. The official CIC web page lists the seven broad categories and constituent attack types. This supports the conceptual attack taxonomy.

The local files have no row-level label column according to the saved audit. The implementation assigns every row the name of its immediate parent directory; this is a project convention, not a label recovered from an official target column. The local folders' names appear consistent with many paper attack names, but exact normalization, spelling, and folder-to-scenario assignment have not been compared against a publisher-supplied label manifest.

In the 34-label project mapping, `Benign_Final` becomes `Benign` because the loader maps any parent folder containing “benign”, “normal”, or “legitimate” to `Benign`. The paper establishes that a benign class exists, but the authoritative materials inspected here do not establish `Benign_Final` as the official source folder name or explicitly prescribe this string mapping. Thus the mapping is reasonable as a local normalization, but **not source-verified**. The project should retain the original folder value and derived value in provenance (it currently does in the sample manifest) and describe the resulting target as folder-derived.

## 4. Provenance, checksum, citation and license gaps

Present: config source-page URL and year; audited local file paths, sizes, SHA-256 values; sample SHA-256 and preparation settings; official publication metadata and a usable citation.

Missing or unresolved: local retrieval date; original download form/account/session or custodian record; exact archive/release identifier; archive checksum or publisher checksum to compare; source URL captured at download time; evidence that the local README and CSVs came together from the official package; named dataset-specific license; independent label manifest linking each folder/file/row to the attack scenario. The final experiment JSON records package versions and hardware but has `code_revision: null`, so it does not identify the exact source revision used. The existing SHA-256 hashes provide local integrity and repeatability, not publisher provenance.

Recommended citation: Neto et al. (2023), *Sensors*, 23(13), 5941, https://doi.org/10.3390/s23135941, together with the CIC dataset page. Do not cite the paper as proof that these exact local bytes came from the publisher.

## 5. Suitability for this project

CICIoT2023 is suitable for exploratory supervised intrusion detection/classification: the publisher designed it for malicious-versus-benign and multiclass traffic classification, and the paper evaluates such tasks. Its CSV data are extracted packet-window traffic features from a controlled IoT testbed. Here, the project additionally uses a deterministic cap of 5,000 rows per folder, which substantially changes class prevalence, and assigns labels from unverified local folders. Current performance therefore describes only this derived sample and label procedure.

It is not direct evidence about dynamic server load balancing: it does not measure the project's server state, request assignment, throughput, latency, or load-balancer decisions. The study title and downstream reporting must keep the intrusion-classification work separate from simulation-based load-balancing evaluation. The dataset's controlled IoT attack scenarios also limit generalization to production networks.

## 6. Verified facts, assumptions, limitations

| Status | Determination |
|---|---|
| Verified from official source | CICIoT2023 is a CIC/UNB dataset; the paper describes 105 IoT devices, 33 attacks in seven categories, benign traffic, CSV/PCAP data, and intrusion-classification use. |
| Verified from local audit | The audited local tree had 34 directories, 309 CSVs, 39 consistent feature columns and 46,776,700 rows; the sample and local source files have recorded hashes. |
| Verified from local code | Target values are synthesized from immediate parent folder names; any folder containing “benign” maps to `Benign`; no independent target file is consulted. |
| Verified mismatch | Local `README_CSV.pdf` describes shuffled/combined data with a `label` feature; local audit/code describe separate folder files with no raw label column. |
| Reasonable but unverified assumption | The folder taxonomy reflects the intended scenario labels and `Benign_Final` means benign traffic. |
| Unverified | Exact local package provenance, official release/version identity, source-side checksum match, file-level ground truth, `Benign_Final`'s official status, and faculty/team approval. |
| Limitation | Local hashes show that the audited bytes can be identified again; they do not authenticate publisher origin. Sample balancing, unknown capture/session independence, and the folder-derived targets constrain inference. |

## Sources

1. [Official CICIoT2023 dataset page](https://www.unb.ca/cic/datasets/iotdataset-2023.html) and its [download form](https://cicresearch.ca/IOTDataset/CIC_IOT_Dataset2023/).
2. Neto, E.C.P. et al. (2023). “CICIoT2023: A Real-Time Dataset and Benchmark for Large-Scale Attacks in IoT Environment.” *Sensors*, 23(13), 5941. [https://doi.org/10.3390/s23135941](https://doi.org/10.3390/s23135941).
3. [CIC datasets FAQ](https://www.unb.ca/cic/datasets/) for reuse/citation guidance and its note about licensing information.
4. Supplied local source-package README (`README_CSV.pdf`), extracted with macOS PDFKit on 2026-11-27. It states 309 CSV files, combined/shuffled data and a `label` feature. The local raw files were not changed during this audit.
5. Repository records: `backend/config/cic-iot2023-final.json`, `backend/app/features/iot_loader.py`, `backend/app/features/iot_preparation.py`, `docs/audits/cic_iot2023_audit.json`, and the adjacent prepared-sample manifest.
