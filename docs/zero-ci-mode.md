# Zero-CI completion mode

During the portfolio completion pass, GitHub Actions should be used only as a deliberate release gate. Source review, code changes, tests, documentation, and verification scripts are prepared first; CI is then invoked manually on a frozen candidate.

Reason: automatic pull-request runs were consuming minutes without necessarily reaching meaningful test execution.

Policy:
- no automatic CI on push or pull request during active completion work;
- keep `workflow_dispatch` for deliberate remote verification;
- use direct local verification commands as the source acceptance contract;
- do not repeatedly rerun infrastructure failures;
- run expensive Android/desktop/browser jobs only on a frozen release candidate.
