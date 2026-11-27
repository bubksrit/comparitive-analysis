# CIC-IoT2023 local dataset audit

> CIC-IoT2023 is an optional alternative; team/faculty dataset approval is not confirmed. Local file content was audited, but origin and label truth were not independently verified. See the [provenance and ground-truth review](cic_iot2023_provenance_and_ground_truth.md).

Official source references: [CICIoT2023 dataset page](https://www.unb.ca/cic/datasets/iotdataset-2023.html); Neto et al., “CICIoT2023: A Real-Time Dataset and Benchmark for Large-Scale Attacks in IoT Environment,” *Sensors* 23(13), 5941 (2023), [doi:10.3390/s23135941](https://doi.org/10.3390/s23135941). These references describe the published dataset and taxonomy; they do not authenticate the local files.

- Audit date: 2026-11-27
- Dataset root: `<LOCAL_CIC_IOT2023_CSV_ROOT>`
- Top-level directories: 34
- CSV files: 309
- Total input size: 8,943,771,319 bytes
- Rows scanned: 46,776,700
- Schema mismatches: 0
- Scan errors: 0
- Duplicate rows within chunks (lower bound): 13,711,870

## Folder-derived class distribution (multiclass)

| Folder label | Rows |
|---|---:|
| Backdoor_Malware | 3,218 |
| Benign | 1,098,191 |
| BrowserHijacking | 5,859 |
| CommandInjection | 5,409 |
| DDoS-ACK_Fragmentation | 285,075 |
| DDoS-HTTP_Flood | 28,790 |
| DDoS-ICMP_Flood | 7,200,501 |
| DDoS-ICMP_Fragmentation | 452,490 |
| DDoS-PSHACK_FLOOD | 4,094,772 |
| DDoS-RSTFINFLOOD | 4,045,279 |
| DDoS-SYN_Flood | 4,059,179 |
| DDoS-SlowLoris | 23,426 |
| DDoS-SynonymousIP_Flood | 3,598,133 |
| DDoS-TCP_Flood | 4,497,649 |
| DDoS-UDP_Flood | 5,412,231 |
| DDoS-UDP_Fragmentation | 286,925 |
| DNS_Spoofing | 178,898 |
| DictionaryBruteForce | 13,064 |
| DoS-HTTP_Flood | 71,861 |
| DoS-SYN_Flood | 2,028,836 |
| DoS-TCP_Flood | 2,671,430 |
| DoS-UDP_Flood | 3,072,993 |
| MITM-ArpSpoofing | 307,560 |
| Mirai-greeth_flood | 991,834 |
| Mirai-greip_flood | 751,646 |
| Mirai-udpplain | 890,574 |
| Recon-HostDiscovery | 134,378 |
| Recon-OSScan | 98,259 |
| Recon-PingSweep | 2,262 |
| Recon-PortScan | 82,284 |
| SqlInjection | 5,245 |
| Uploading_Attack | 1,252 |
| VulnerabilityScan | 373,351 |
| XSS | 3,846 |

## Data quality counts

| Column | Missing | Infinite | Non-numeric parse errors |
|---|---:|---:|---:|
| Header_Length | 0 | 0 | 0 |
| Protocol Type | 0 | 0 | 0 |
| Time_To_Live | 0 | 0 | 0 |
| Rate | 0 | 1,037 | 0 |
| fin_flag_number | 1 | 0 | 0 |
| syn_flag_number | 1 | 0 | 0 |
| rst_flag_number | 1 | 0 | 0 |
| psh_flag_number | 1 | 0 | 0 |
| ack_flag_number | 1 | 0 | 0 |
| ece_flag_number | 1 | 0 | 0 |
| cwr_flag_number | 1 | 0 | 0 |
| ack_count | 1 | 0 | 0 |
| syn_count | 1 | 0 | 0 |
| fin_count | 1 | 0 | 0 |
| rst_count | 1 | 0 | 0 |
| HTTP | 1 | 0 | 0 |
| HTTPS | 1 | 0 | 0 |
| DNS | 1 | 0 | 0 |
| Telnet | 1 | 0 | 0 |
| SMTP | 1 | 0 | 0 |
| SSH | 1 | 0 | 0 |
| IRC | 1 | 0 | 0 |
| TCP | 1 | 0 | 0 |
| UDP | 1 | 0 | 0 |
| DHCP | 1 | 0 | 0 |
| ARP | 1 | 0 | 0 |
| ICMP | 1 | 0 | 0 |
| IGMP | 1 | 0 | 0 |
| IPv | 1 | 0 | 0 |
| LLC | 1 | 0 | 0 |
| Tot sum | 1 | 0 | 0 |
| Min | 1 | 0 | 0 |
| Max | 1 | 0 | 0 |
| AVG | 2 | 0 | 0 |
| Std | 704 | 0 | 0 |
| Tot size | 3 | 0 | 0 |
| IAT | 3 | 0 | 0 |
| Number | 3 | 0 | 0 |
| Variance | 705 | 0 | 0 |

## Limitations

- The 13,711,870 duplicate-row value above is a within-chunk lower bound only; cross-chunk and cross-file duplicates are not counted by this report. A later global exact audit is incomplete; see the [current duplicate-audit status](cic_iot2023_duplicate_audit_status.md). No exact global duplicate count is available.
- Folder labels are derived from names and not checked against independent row labels.
- The official dataset page describes 33 attacks in seven categories; the local 34 folders represent benign plus individual attack folders. This is not evidence of faculty approval or dataset provenance.
- The local `README_CSV.pdf` describes combined/shuffled CSVs with a `label` feature, unlike the local files summarized here. The local 39-column schema also differs from fields listed in the official CIC feature summary. Treat this as a local structural audit, not a verified official-release match; details are in the provenance review above.
- Per-file relative paths and byte sizes are recorded in the companion JSON report.
