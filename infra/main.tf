# IaC for the free-tier stack: Vercel (hosting) + Neon (serverless Postgres).
# No Azure resources here — kept intentionally off this project to stay $0.
#
# NOTE: vercel/vercel and kislerdm/neon are evolving providers (the Neon one is
# community-maintained). Attribute names below match their docs as of writing —
# run `terraform providers schema` or check registry.terraform.io before
# `terraform apply` if a plan errors on an unknown attribute.

terraform {
  required_version = ">= 1.7"
  required_providers {
    vercel = {
      source  = "vercel/vercel"
      version = "~> 1.0"
    }
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.6"
    }
  }
}

variable "vercel_api_token" {
  sensitive = true
}

variable "neon_api_key" {
  sensitive = true
}

variable "env" {
  default = "dev"
}

variable "github_repo" {
  description = "owner/repo on GitHub, e.g. yourname/HSK-Vocabulary-Frequency"
  type        = string
}

provider "vercel" {
  api_token = var.vercel_api_token
}

provider "neon" {
  api_key = var.neon_api_key
}

# --- Neon: free-tier serverless Postgres ---
resource "neon_project" "db" {
  name       = "hsk-frequency-${var.env}"
  region_id  = "aws-ap-southeast-1"
  pg_version = 16
}

# --- Vercel: free Hobby-tier project hosting frontend + FastAPI serverless function ---
resource "vercel_project" "app" {
  name      = "hsk-vocabulary-frequency"
  framework = "vite"

  git_repository = {
    type = "github"
    repo = var.github_repo
  }

  build_command    = "cd frontend && npm install && npm run build"
  output_directory = "frontend/dist"
}

locals {
  # neon_project's default connection branch/role/database outputs —
  # verify exact attribute names against the provider docs (they vary by version).
  db_host     = neon_project.db.database_host
  db_user     = neon_project.db.database_user
  db_password = neon_project.db.database_password
  db_name     = neon_project.db.database_name
}

resource "vercel_project_environment_variable" "db_host" {
  project_id = vercel_project.app.id
  key        = "DB_HOST"
  value      = local.db_host
  target     = ["production", "preview"]
}

resource "vercel_project_environment_variable" "db_user" {
  project_id = vercel_project.app.id
  key        = "DB_USER"
  value      = local.db_user
  target     = ["production", "preview"]
}

resource "vercel_project_environment_variable" "db_password" {
  project_id = vercel_project.app.id
  key        = "DB_PASSWORD"
  value      = local.db_password
  target     = ["production", "preview"]
  sensitive  = true
}

resource "vercel_project_environment_variable" "db_name" {
  project_id = vercel_project.app.id
  key        = "DB_NAME"
  value      = local.db_name
  target     = ["production", "preview"]
}

resource "vercel_project_environment_variable" "db_sslmode" {
  project_id = vercel_project.app.id
  key        = "DB_SSLMODE"
  value      = "require"
  target     = ["production", "preview"]
}

output "vercel_project_url" {
  value = "https://${vercel_project.app.name}.vercel.app"
}

output "neon_project_id" {
  value = neon_project.db.id
}
