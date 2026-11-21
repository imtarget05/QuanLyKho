# Recruiter evidence — QuanLyKho

Public baseline: [`2e753d1cf3025342f6e6fd5424a5634852fac49c`](https://github.com/imtarget05/QuanLyKho/commit/2e753d1cf3025342f6e6fd5424a5634852fac49c). These results are from the [GitHub Actions CI run on 2026-11-17](https://github.com/imtarget05/QuanLyKho/actions/runs/44129715048), not from the current uncommitted local worktree.

| CI job | Evidence |
| --- | --- |
| `test` (PostgreSQL 16 service, Python 3.11) | 1,285 passed, 8 skipped, 1 xfailed, 25 warnings in 541.68s; coverage XML uploaded as an artifact |
| `frontend-web` | 355 Flutter tests passed |
| `lint`, `Secret Guard` | Both jobs succeeded |
| `build`, `worker-typecheck`, `SonarQube scan` | Jobs succeeded; review each job's checks before making a narrower security or quality claim |

The older [f65f962 baseline](baseline-f65f962.md) verified two demo backend tests and 355 frontend tests on 2026-11-12. It remains historical evidence, not the current backend suite count. A green CI run confirms the configured tests executed; it does not prove every approval race or cross-branch access case exists in the suite.

At this public SHA, concrete regression cases include `test_two_checkers_concurrent_approve` and `test_reversal_creates_new_balanced_journal` in `backend/tests/test_acceptance_qa.py`, `test_two_concurrent_approvals_do_not_double_spend` in `backend/tests/test_cash_sim_money_path.py`, and scoped branch-B exclusion cases in `backend/tests/test_b2_authorization_scope.py`. These are stronger references than the old two-test demo baseline; review each case's assertions when presenting the specific guarantee.

## Two-minute demo

1. Show a maker creating a request and a different checker approving it; explain the server-side self-approval guard.
2. Show the resulting ledger entries and audit event, then a reversal that preserves the original journal.
3. Open the CI run above and point to the exact SHA and backend test summary. Describe any concurrency or branch-scope cases that still need dedicated proof.

With a disposable `bankops_test` PostgreSQL database and the documented demo environment, the executable proof is:

```sh
cd backend
poetry run pytest tests/test_portfolio_ai_checker_demo.py tests/test_acceptance_qa.py -q
```

This runs the maker/checker/audit demo and the acceptance cases for concurrent approval and ledger reversal. It must not point at a development or production database.
