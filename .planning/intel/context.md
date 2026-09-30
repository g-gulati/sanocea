# Project Context & Environment

**Analysis Date:** 2026-09-30

## Repository Profile
- **Project Name:** SANOCEA Autonomous Commerce Operating System & SEO Sentinel Stack
- **Architecture:** Dual-Engine Asynchronous Event-Driven Architecture
- **Primary Languages:** TypeScript 5.3+, Python 3.11+, JavaScript/React 19
- **Production Host:** Ubuntu 24.04 LTS (`/opt/sanocea/repo`)
- **Web Deployment:** `/var/www/sanocea/current` (Vite SPA served over HTTPS)
- **Active Background Services:**
  - `sanocea-seo-worker.service` (Systemd active)
  - `sanocea-api.service` (Systemd active)
- **Live Integrations:**
  - Google Search Console API (`sc-domain:sanocea.com`) via service account
  - SQLite WAL (`packages/seo-stack/seo_monitoring.sqlite`)
  - WhatsApp Cloud API simulator & transport
