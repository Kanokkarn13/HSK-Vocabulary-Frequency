# DevSecOps Pipeline

Pipeline defined in: [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml)
IaC defined in: [`infra/main.tf`](../infra/main.tf)

Every tool in this stack runs on its free tier — see the cost notes at the end
before changing anything here.

---

## Pipeline Stages

```
Push to main/develop, or PR to main
      │
      ▼
┌─────────────┐
│  Test       │  pytest + coverage report
└──────┬──────┘
       │ (on success)
       ▼
┌─────────────┐
│  Security   │  Bandit (SAST) + SonarCloud (quality + hotspots)
└──────┬──────┘
       │ (on success)
       ▼
┌─────────────┐
│  Terraform  │  fmt/validate/plan on every run; apply only on push to main
└─────────────┘

Deploy is NOT a job in this workflow — see "Deployment" below.
```

PRs run Test + Security + `terraform plan` (no `apply`, no deploy) — this is the
review gate. Merging to `main` runs the same stages and then `terraform apply`.

---

## Why GitHub Actions instead of Azure Pipelines

This project used to target Azure DevOps for CI/CD. Two things made that a bad
fit for a zero-budget portfolio project:

1. Microsoft stopped allowing new **public** Azure DevOps projects (anti-abuse
   policy), and public visibility is what unlocks free unlimited Pipeline
   minutes — private projects default to 0 parallel jobs and need a manual
   grant request.
2. SonarCloud's free tier also requires a public repo, and Azure DevOps
   couldn't provide one anymore either.

GitHub public repos get unlimited free Actions minutes with no approval step,
and satisfy SonarCloud's public-repo requirement directly — so the whole
toolchain moved there.

---

## Security & Quality Scanning

### Bandit (SAST)

Scans Python source for common security issues: SQL injection, shell
injection, use of `eval`, hardcoded secrets, etc.

```bash
pip install bandit
bandit -r backend/ etl/ -f json -o bandit-report.json
bandit -r backend/ etl/ -ll  # only medium+ severity, print to console
```

The workflow uses `|| true` so findings don't fail the build — tighten this
to a hard gate once the baseline is clean.

### Dependabot (Dependency CVEs)

Configured in [`.github/dependabot.yml`](../.github/dependabot.yml) — a native
GitHub feature, free with no signup or token, covering `requirements/`
(pip), `frontend/` (npm), the workflow file itself (github-actions), and
`infra/` (terraform). It checks weekly and opens a PR per outdated/vulnerable
dependency directly, rather than just reporting a finding like Snyk/Safety
would — this replaced both of those in the pipeline for exactly that reason.

### SonarCloud

Code quality + maintainability + duplicate-code + additional security
hotspots. Free only for public repos — needs `SONAR_TOKEN` (from
sonarcloud.io > My Account > Security), plus a `sonar-project.properties` at
the repo root with your `sonar.organization` / `sonar.projectKey`.

---

## Infrastructure as Code — Terraform

`infra/main.tf` provisions:

- A **Neon** project (`neon_project`) — free-tier serverless Postgres.
- A **Vercel** project (`vercel_project`) — free Hobby tier, linked to this
  GitHub repo via the `git_repository` block, plus the DB env vars
  (`DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`/`DB_SSLMODE`) wired from the
  Neon outputs straight into Vercel's project environment variables.

Required repo secrets for the `terraform` job (Settings → Secrets and
variables → Actions):

| Secret | Where to get it |
|---|---|
| `VERCEL_TOKEN` | vercel.com → Account Settings → Tokens |
| `NEON_API_KEY` | console.neon.tech → Account → API Keys |
| `SONAR_TOKEN` | sonarcloud.io → My Account → Security |

Run locally the same way the pipeline does:

```bash
cd infra
terraform init
terraform plan \
  -var="vercel_api_token=$VERCEL_TOKEN" \
  -var="neon_api_key=$NEON_API_KEY" \
  -var="github_repo=yourname/HSK-Vocabulary-Frequency"
```

Only `terraform apply` on merges to `main` in CI — don't apply from a feature
branch, since the plan is meant to represent what's actually live.

---

## Deployment

No explicit deploy job. Once `infra/main.tf`'s `vercel_project.git_repository`
points at this repo, Vercel's own GitHub integration takes over: a preview
deployment per PR, a production deployment on every push to `main` — free,
automatic, and zero extra GitHub Actions minutes spent on it. See
[Deploying to Vercel + Neon](deploy-vercel.md) for the manual first-time setup
and the data-loading steps Terraform doesn't cover.

---

## Uptime Monitoring — UptimeRobot

Not part of the pipeline — configured directly in the UptimeRobot dashboard
(free tier: 50 monitors, 5-minute interval). Point one HTTP(s) monitor at the
deployed Vercel URL's `/health` endpoint.

---

## Running Checks Locally

```bash
pip install bandit pytest pytest-cov
pytest tests/ -v --cov=backend --cov=etl
bandit -r backend/ etl/ -ll
```

`act` (nektos/act) can also run this workflow locally against a real Docker
runner if you want to test workflow changes before pushing.

---

## What NOT to provision (costs money)

Nothing in this stack should. If you ever add anything here, check its
pricing page for a "free tier requires X" catch (public repo, request-only
grant, usage cap) before wiring it into the pipeline — several of the
now-removed Azure pieces looked free until you hit exactly that kind of catch.
