# Analytics & SEO

Covers Phase 7 (Analytics) and Phase 8 (SEO) from the README's development
phases table. Planned, not yet implemented. All free tier — see
[DevSecOps Pipeline](devsecops.md) for the related security tooling
(OWASP ZAP, Cloudflare) and the "must stay 100% free" constraint that
applies here too.

---

## Analytics — PostHog

Free tier, no overlap with anything already in the stack (UptimeRobot only
checks uptime, not usage). Tracks page views / word searches / filter usage
on the deployed dashboard.

## SEO

| Tool | Purpose | Cost |
|---|---|---|
| Google Search Console | Indexing status, crawl errors, search query data | Free |
| Google Lighthouse | Technical audit — performance, accessibility, SEO, best practices | Free (built into Chrome DevTools / CI) |
| Ahrefs Webmaster Tools | Full-site technical crawl + backlink monitoring for a *verified* domain | Free (verified-site tier) |

**Ahrefs Webmaster Tools chosen over Ubersuggest:** this project is a
single-site portfolio dashboard, not a content/blog site competing for
keyword rankings. What it needs is a technical audit (crawl errors, broken
links, indexing) of its own domain, which Ahrefs Webmaster Tools gives
unlimited/free once the domain is verified. Ubersuggest is a
keyword-research tool aimed at content marketing, rate-limited to a few free
searches/day even for your own site — the wrong shape of tool for this use
case, so it was dropped to avoid stacking two overlapping SEO tools
(consistent with dropping Snyk/`safety` in favor of Dependabot — see
[DevSecOps Pipeline](devsecops.md#dependabot-dependency-cves)).

## Domain note

Google Search Console and Ahrefs Webmaster Tools both work fine against the
current `hsk-vocabulary-frequency.vercel.app` subdomain (they just need
ownership verification, not DNS control) — unlike Cloudflare, which needs an
owned custom domain. No blocker here.
