# Project quality rules

These rules apply to every code change in this repository.

## Tests and SonarCloud

- Run the same test command used by CI before pushing:
  `pytest tests/ --cov=backend --cov=etl --cov-report=xml -v`.
- A test or quality-gate failure must be fixed at its root cause. Do not use
  `|| true`, skip markers, or broad Sonar exclusions to hide failures.
- SonarCloud must consume `coverage.xml` produced by the `test` job. Do not
  rerun the suite in the security job with a different environment; this keeps
  the quality result deterministic and tied to the tested revision.
- New production code under `backend/` or `etl/` needs regression tests. Keep
  coverage exclusions limited to orchestration/integration glue that is tested
  by Airflow or database smoke tests.
- If a source file is changed, run the focused tests for that module and then
  the full suite before opening or updating a pull request.

## CI and quality-gate changes

- Keep `sonar-project.properties` and `.github/workflows/ci-cd.yml` in sync.
- Treat the SonarCloud quality gate as required. A missing token may skip the
  external scan on Dependabot/fork runs, but it must never turn a failed test
  or missing coverage report into a successful check.
- Do not modify historical commit statuses or rewrite `master` to hide old
  failures. Fix the code/config in a new commit and preserve the audit trail.
