# DevSecOps Pipeline

Pipeline defined in: [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml)
IaC defined in: [`infra/main.tf`](../infra/main.tf)

Every tool in this stack runs on its free tier — see the cost notes at the end
before changing anything here.

---

## Pipeline Stages

```
Push to master/develop, or PR to master
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
│  Terraform  │  fmt + validate only (syntax-level, no state needed)
└─────────────┘

Deploy is NOT a job in this workflow — see "Deployment" below.
```

PRs and pushes to `master` run the same three stages. `terraform plan`/`apply`
are **not** run in CI at all — see the IaC section below for why.

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

**Watch the `terraform` ecosystem PRs closely before merging.** Dependabot
bumped the `vercel/vercel` provider constraint from `~> 1.0` to `~> 5.3` in
one PR — a 4-major-version jump that made `sensitive` a required argument on
`vercel_project_environment_variable` (previously optional) and broke
`terraform validate`. Unlike a Python patch-version bump, a Terraform
provider major-version bump can change resource schemas outright. Always run
`terraform validate`/`plan` locally against a Dependabot terraform PR before
merging, the same way you would review any other breaking-change upgrade.

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

**State is local-only.** There's no remote backend configured — `infra/main.tf`
has no `backend` block, so `terraform apply` writes to
`infra/terraform.tfstate` on whatever machine runs it, and that file is
gitignored (it contains the Neon DB password in plaintext). That means
`plan`/`apply` only run **locally**, by hand, from `infra/terraform.tfvars`
(also gitignored — see `infra/terraform.tfvars.example` for the format):

```bash
cd infra
terraform init
terraform plan
terraform apply
```

CI only runs `terraform fmt -check` and `terraform validate` — both are
syntax/schema checks that need no state and no provider credentials at all.
CI does **not** run `plan` or `apply`. The first version of this pipeline did
run `apply` automatically on every push to `master`, but since a CI runner
has no access to the local state file, that apply always started from a
blank slate and tried to recreate the Neon/Vercel projects that already
existed — failing with "already exists" conflicts. A shared remote backend
(e.g. Terraform Cloud's free tier) would fix that properly if this project
ever needs a second operator or a CI-driven apply; for a single-person
portfolio project where infra changes are rare, local-only apply is simpler
and was the right call.

Required secrets for running Terraform locally (not GitHub secrets — just
values you paste into `infra/terraform.tfvars`):

| Value | Where to get it |
|---|---|
| `vercel_api_token` | vercel.com → Account Settings → Tokens |
| `neon_api_key` | console.neon.tech → Account → API Keys |
| `neon_org_id` | console.neon.tech → Organization Settings → General (required by Neon's API even for a personal account) |

Note: Neon rejects the provider's default 24h history-retention window on
free-tier accounts (max is 6h) — `infra/main.tf` sets
`history_retention_seconds = 21600` explicitly to stay within that.

**Watch Dependabot's `terraform` PRs before merging one that touches
`infra/main.tf` provider constraints** — see the Dependabot section above for
the vercel provider major-version break we hit.

---

## Deployment

No explicit deploy job. Once `infra/main.tf`'s `vercel_project.git_repository`
points at this repo, Vercel's own GitHub integration takes over: a preview
deployment per PR, a production deployment on every push to `master` — free,
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
