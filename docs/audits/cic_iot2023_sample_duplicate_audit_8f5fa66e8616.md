# CIC-IoT2023 prepared sample duplicate audit

- Scope: prepared development sample only
- Sample rows: 160,578
- Sample SHA-256: `8f5fa66e8616ba199bdc2b634d9cf235ee77d1555babf88e6c07c33ed5cd12eb`
- Exact full-record duplicate occurrences retained: 2,524
- Identical feature-vector duplicate occurrences retained: 3,794
- Global raw-dataset duplicate audit: incomplete; no global count is available.
- Rows removed: 0

## Class counts

| Label | Rows |
|---|---:|
| Backdoor_Malware | 3,218 |
| Benign | 5,000 |
| BrowserHijacking | 5,000 |
| CommandInjection | 5,000 |
| DDoS-ACK_Fragmentation | 5,000 |
| DDoS-HTTP_Flood | 5,000 |
| DDoS-ICMP_Flood | 5,000 |
| DDoS-ICMP_Fragmentation | 5,000 |
| DDoS-PSHACK_FLOOD | 5,000 |
| DDoS-RSTFINFLOOD | 5,000 |
| DDoS-SYN_Flood | 5,000 |
| DDoS-SlowLoris | 5,000 |
| DDoS-SynonymousIP_Flood | 5,000 |
| DDoS-TCP_Flood | 5,000 |
| DDoS-UDP_Flood | 5,000 |
| DDoS-UDP_Fragmentation | 5,000 |
| DNS_Spoofing | 5,000 |
| DictionaryBruteForce | 5,000 |
| DoS-HTTP_Flood | 5,000 |
| DoS-SYN_Flood | 5,000 |
| DoS-TCP_Flood | 5,000 |
| DoS-UDP_Flood | 5,000 |
| MITM-ArpSpoofing | 5,000 |
| Mirai-greeth_flood | 5,000 |
| Mirai-greip_flood | 5,000 |
| Mirai-udpplain | 5,000 |
| Recon-HostDiscovery | 5,000 |
| Recon-OSScan | 5,000 |
| Recon-PingSweep | 2,262 |
| Recon-PortScan | 5,000 |
| SqlInjection | 5,000 |
| Uploading_Attack | 1,252 |
| VulnerabilityScan | 5,000 |
| XSS | 3,846 |

## Limitations

- The sample audit does not estimate or establish global raw-dataset duplicate totals.
- Folder-derived labels are provenance labels, not independently verified ground truth.
- No capture/session independence is inferred from feature equality or source-file boundaries.
