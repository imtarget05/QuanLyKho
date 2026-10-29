# Eval Report Summary — QuanLyKho (P3.6/P3.7)

| Field | Value |
|-------|-------|
| **Task** | P3.6/P3.7 — Python Evaluation Harness output + evidence packaging |
| **Commit SHA** | `9f877c2ad25ee5639c7a96b3c69037b2f40ff63c` (HEAD at packaging) |
| **Command** | `python3 /Users/mainguyenbinhtan/Downloads/eval/harness.py` |
| **Output** | Overall **100.0/100**; 6/6 dimensions at 100; gaps: none; secrets: 60 (all masked/placeholder) |
| **Status** | VERIFIED |

## Dimension scores (QuanLyKho)

| Dimension | Score | Max | Status |
|-----------|-------|-----|--------|
| architecture | 100 | 100 | PASS |
| business_logic | 100 | 100 | PASS |
| features | 100 | 100 | PASS |
| flows | 100 | 100 | PASS |
| devops | 100 | 100 | PASS |
| cloud | 100 | 100 | PASS |
| **Overall** | **100.0** | **100** | **PASS** |

## Validation results (harness)

| Tool | Available | Result |
|------|-----------|--------|
| kustomize | No | n/a |
| terraform | No | n/a |
| pytest | Yes (python3) | exit_code=1, ok=False — `No module named pytest` (Python 3.14 sandbox limitation) |

## Source

- `/Users/mainguyenbinhtan/Downloads/eval/report.json` — QuanLyKho repo block (711 files scanned, overall 100.0, 0 gaps, 60 secrets).
- `/Users/mainguyenbinhtan/Downloads/eval/REPORT.md` — human-readable evaluation report.

## Caveat

The harness `pytest` validation could not execute the backend suite because `pytest` is not installed under Python 3.14.7. Backend test evidence is instead carried forward from `QA_REPORT.md` / local venv runs (see `01-backend-test-results.md`). This is an environment limitation explicitly permitted by the task rules; it does not affect the dimension scores which are derived from static artifact scanning.
