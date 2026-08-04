# Security policy

This repository contains an educational ETL pipeline and a small API. Treat
all local credentials, source documents, and generated datasets as sensitive
unless they are explicitly documented as public.

## Supported branch

Security fixes are applied to `master` and the current deployment pull
request. Older branches are not guaranteed to receive security updates.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's
private **Report a vulnerability** form under the repository's **Security**
tab. Include:

- the affected file, endpoint, or workflow;
- reproduction steps or a minimal proof of concept;
- the potential impact and any known workaround; and
- whether the report involves credentials or private learning data.

If private reporting is unavailable, contact the repository maintainer through
their verified GitHub profile and request a private channel. Do not include
secrets in the first message.

## Repository rules

- Never commit `.env` files, API keys, database passwords, Airflow auth files,
  Terraform variable/state files, or private source documents.
- Use GitHub Actions secrets for CI credentials. The SonarCloud token must be
  provided as `SONAR_TOKEN`; Dependabot/fork runs may skip the external scan
  when GitHub withholds secrets.
- Keep generated validation reports and local editor/assistant state ignored.
  Hand-written test fixtures may be force-added deliberately.
- Keep Airflow publishing fail-closed. Production writes require an explicit
  `HSK_PUBLISH_ENABLED=true` and must pass the staging/validation gates first.
- Do not weaken tests, SonarCloud quality gates, or security scans to make a
  check green. Fix the underlying issue and retain the audit trail.

## Automated checks

Pull requests run pytest with coverage, Bandit, SonarCloud, Airflow DAG and
Compose checks, and Terraform validation. A change is ready only when the
required checks pass and no secrets or private data are added to the diff.
