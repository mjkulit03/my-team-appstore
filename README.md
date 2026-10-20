# My Team — Software Suite Platform

A full-stack storefront and autonomous command centre for a suite of thirteen business
systems, backed by three "AI employees" (Marketing, Sales, Accounting) and a
notification pipeline that escalates anything needing a human decision.

**Everything runs locally and free.** No LLM API keys, no paid services. The agents are
deterministic rule engines, so output is reproducible and the whole suite deploys to
GitHub Actions or any free Python host.

```
Storefront  /         App Store  /app-store      AI dashboard  /dashboard
Control panel  /control/login
```

---

## 1. Quick start

Full operating procedure, demo credentials and troubleshooting:
**[`docs/RUNBOOK.md`](docs/RUNBOOK.md)**.

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in the values you need (all optional to start)
uvicorn main:app --reload --port 8000
```

| URL | What it is |
|---|---|
| `http://127.0.0.1:8000/` | Public storefront — catalog + product landing pages |
| `http://127.0.0.1:8000/app-store` | Static app store (the page GitHub Pages publishes) |
| `http://127.0.0.1:8000/dashboard` | AI Command Center — Marketing / Sales / Accounting tabs |
| `http://127.0.0.1:8000/control/login` | Control panel (locked until an account exists) |
| `http://127.0.0.1:8000/control/settings/users` | User accounts (admin only) |
| `http://127.0.0.1:8000/docs` | Interactive API docs |

`.env` is loaded automatically at startup. Real environment variables always win
over the file, so CI secrets and shell exports are never overridden by a stray
`.env`. If you prefer not to use the file at all, export the variables in your
shell instead — `uvicorn` reads `os.environ` directly.

Run the tests:

```bash
python -m pytest
```

Run the notification worker:

```bash
python -m notifications.worker --dry-run   # report what would be sent
python -m notifications.worker             # actually send
```

---

## 2. The product catalog

Thirteen systems, defined once in `catalog/products.py` — the single source of truth
for the storefront, the app store, the Marketing AI's copy, and the Sales AI's
targeting.

| Product | Category | PHP/mo | Approval gate |
|---|---|---|---|
| Hardware Management System | IT Asset Management | ₱1,490 | — |
| Clinic Inventory System | Healthcare Inventory | ₱2,490 | **required** (regulated) |
| Office Supplies Inventory System | Inventory & Procurement | ₱1,190 | on truncation |
| IT Asset Management System | IT Asset Management | ₱2,890 | on truncation |
| Service Management Request System | Service Management | ₱1,990 | on truncation |
| Offsite Log-In Management System (Time Keeping) | Time & Attendance | ₱1,490 | **required** (regulated) |
| Grocery Sales and Inventory Management System | Retail & Sales | ₱1,790 | on truncation |
| Student Record with Facial Recognition System | Education & Attendance | ₱3,290 | **required** (biometric) |
| HRIS — Human Resource Information System | HR & Payroll | ₱2,690 | on truncation |
| Project Management System | Project & Work Management | ₱1,990 | on truncation |
| Offline POS System | Retail & Sales | ₱1,590 | on truncation |
| Cybersecurity Games | Security Awareness | ₱1,290 | on truncation |
| Online File Tracking System | Records & Document Management | ₱1,490 | on truncation |

Each product page renders social copy drafted on the fly by the Marketing AI from that
product's own catalog entry.

Some entries carry a `demo_url` (live public preview) or a `repo_url` (source
repository); the storefront and app store render those links automatically.

| Live demo | Product |
|---|---|
| <https://mjkulit03.github.io/offsite-employee-login/> | Offsite Log-In Management System |
| <https://mjkulit03.github.io/file-tracking/> | Online File Tracking System |

### The app store

`docs/index.html` is a standalone, dependency-free storefront for all thirteen systems,
published to GitHub Pages by `.github/workflows/pages.yml`. It is **generated** from the
catalog, so it can never drift from the products the platform sells:

```bash
python tools/build_store.py      # regenerate docs/index.html
```

Override the contact and repository links with `STORE_GITHUB_URL`, `STORE_REPO_URL` and
`STORE_EMAIL` when building for a different account.

The catalog decides **which** systems exist; `docs/store-content.json` holds the
prices, labels and page copy an administrator may change. `store_content.py` layers
that file over the catalog and refuses bad values (negative or absurd prices,
blank or over-long labels, unknown slugs), so a half-edited file always degrades
to the catalog instead of publishing a broken page.

```bash
python tools/build_store.py --init-content   # seed docs/store-content.json from the catalog
```

### Admin editor

The published store has an **Admin** button in the top right. Signing in there needs a
GitHub **fine-grained token** scoped to this repository with **Contents: Read and
write** (<https://github.com/settings/personal-access-tokens/new>); the classic
`repo` scope works too. The token is kept in the browser tab's `sessionStorage`,
never written to the repository, and the editor uses it to commit
`docs/store-content.json` straight to `main`.

Editing is a normal commit: the Pages workflow rebuilds the store about a minute
after saving, the repo history is the audit trail, and a bad edit can be reverted
with `git revert`. Sign out clears the token from the tab.

### Admin editor with a username and password (hosted)

GitHub Pages is static, so the token dialog above is the only way to edit the
store *without a server*: a password checked in JavaScript could be bypassed with
the browser console, and there would still be nowhere to store the edit.

Host the FastAPI app and that changes. `api/storeadmin.py` adds
`/control/store`, an editor behind the same accounts as the rest of the control
panel — so signing in is `admin` plus `CONTROL_PANEL_PASSWORD`, nothing else.

| Where | What happens |
| --- | --- |
| `GET /control/login?next=/control/store` | Username + password form; returns to the editor after signing in. |
| `GET /control/store` | Page copy, and every product's name, tagline, category, monthly price and setup fee. |
| `POST /control/store` | Validates, writes `docs/store-content.json`, rebuilds `docs/index.html`. Bad prices are refused with the reason; nothing is written. |
| `GET /app-store` | The rebuilt store, served by the same app. |

Roles: `admin` and `operator` may change prices; `analyst` can look but the form
is read-only.

**Keeping the GitHub Pages mirror in sync.** Set `STORE_GITHUB_TOKEN` (a token
with *Contents: Read and write* on this repository) and `STORE_REPO`, and every
save is also committed to `docs/store-content.json`. The Pages workflow then
rebuilds the public site, so the token stays on the server and never reaches a
browser. A rejected push is reported in the editor but never loses the local save.

```bash
STORE_REPO=mjkulit03/my-team-appstore
STORE_GITHUB_TOKEN=github_pat_…     # Contents: Read and write on that repo
STORE_ADMIN_URL=/control/store      # makes the store's Admin button link to the app
```

With `STORE_ADMIN_URL` set, `tools/build_store.py` renders the Admin button as a
link to `/control/store` and omits the token dialog entirely; leave it unset for
the static-only deployment, which keeps that dialog.

#### Deploying it

[Render](https://render.com) runs this app from the repository with no changes to
the code — `render.yaml` at the root is a blueprint for that. Either create a
**New → Blueprint** and point it at the repo, or make a Web Service by hand:

| Setting | Value |
| --- | --- |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/health` |

Then set these environment variables on the service:

- `CONTROL_PANEL_PASSWORD` — the password for the first `admin` account (8+ chars).
  It only creates the account; after that, sign in as `admin` with it.
- `SESSION_SECRET` — `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `STORE_ADMIN_URL=/control/store`, `STORE_REPO`, `STORE_GITHUB_TOKEN` — as above.
- Leave `SEED_DEMO_USERS` unset: demo accounts share one password.

Notes that matter in production:

- The free plan sleeps after inactivity, so the first visit takes a few seconds.
- Its disk is ephemeral: accounts created in `var/` and anything else under
  `DATA_DIR` are lost on redeploy. Set `DATA_DIR` to a mounted disk on a paid
  instance if you need them to survive. Store edits are safe either way once
  `STORE_GITHUB_TOKEN` is set, because they live in the repository.
- Put HTTPS in front (Render does this) and do not set `SEED_DEMO_USERS` on a
  public instance.

### Currency

Prices are in **Philippine peso (PHP)**, with a USD equivalent shown alongside
(`₱1,490/mo · ~$24.59`). Conversion lives in `currency.py` and uses **static,
env-overridable rates** — no FX API is called, so the platform stays free, fast and
deterministic.

```bash
BASE_CURRENCY=PHP     # what the platform prices in
FX_USD=0.0165         # units of USD per 1 PHP; also FX_EUR, FX_GBP, FX_JPY, ...
```

Inspect the live table at `GET /api/control/currency`. The Accounting agent accepts
`PHP, USD, EUR, GBP, JPY, SGD, HKD, AUD, CAD, AED`.

---

## 3. AI employees

Pure functions in `agents/`, each also exposed over HTTP:

| Agent | Function | Endpoint |
|---|---|---|
| Marketing | `run_marketing_agent(description)` → per-channel posts + strategy | `POST /api/agents/marketing` |
| Sales | `run_sales_agent(customer_type)` → cold emails + follow-ups | `POST /api/agents/sales` |
| Accounting | `run_accounting_agent(entries)` → financial status report | `POST /api/agents/accounting` |

The AI dashboard at `/dashboard` drives all three with per-tab prompt boxes, loading and
error states. Control-panel equivalents live under `/api/control/`.

---

## 4. Notifications — the human-in-the-loop pipeline

The agents **never** publish, commit or pay on their own. When something needs a human,
the platform raises an **escalation** and the background worker alerts you.

### Escalation types

| Type | Raised when | Default trigger |
|---|---|---|
| `campaign_approval` | Marketing copy is drafted | Always for Healthcare / Education / Time & Attendance; otherwise only if posts were truncated |
| `high_value_lead` | A storefront inquiry comes in | Estimated value ≥ `LEAD_VALUE_THRESHOLD` (default $3,000) |
| `accounting_anomaly` | An accounting report is produced | Any `critical` alert, or net loss ≥ `ACCOUNTING_ANOMALY_THRESHOLD` (default $1,000) |

### Channels

- **Email** over SMTP (Gmail, Outlook, Yahoo, or your own relay)
- **WhatsApp / webhook** via `NOTIFY_WEBHOOK_PROVIDER`: `generic`, `callmebot` or `ultramsg`

### Configuration — environment variables only

There are **no hardcoded credentials anywhere**. Copy `.env.example` to `.env` and fill in
what you need. `.env` is git-ignored, and CI fails the build if one is ever committed.

Minimum to get email alerts:

```bash
NOTIFY_ENABLED=true
NOTIFY_CHANNELS=email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=<google-app-password>
SMTP_FROM=you@gmail.com
ALERT_EMAILS=ops@yourcompany.com
```

> Gmail requires an **App Password**, not your account password.

For WhatsApp with CallMeBot:

```bash
NOTIFY_CHANNELS=whatsapp
NOTIFY_WEBHOOK_PROVIDER=callmebot
NOTIFY_WEBHOOK_URL=https://api.callmebot.com/whatsapp.php
NOTIFY_WEBHOOK_TOKEN=<your-callmebot-apikey>
NOTIFY_WEBHOOK_PHONE=<15551234567>
```

### Run the worker

```bash
python -m notifications.worker            # deliver pending escalations
python -m notifications.worker --dry-run  # report what would be sent
python -m notifications.worker --json     # machine-readable summary
```

Delivery semantics, so nothing is silently lost:

- **Delivered** → marked notified; never sent twice.
- **Channel configured but failed** → stays pending and **retries on the next run**.
- **No channel configured at all** → marked handled so the cron job doesn't churn, and
  counted in `dropped` so a misconfiguration is visible rather than silent.

The worker exits non-zero when a delivery failed, so a scheduler notices.

---

## 5. Control panel

The control panel is where the AI workforce's work is supervised. It requires a
signed-in session (see §6 for security).

| Panel shows | Where it comes from |
|---|---|
| **Traffic analysis** | Page views, referrer sources, per-product interest, 7-day series, view → inquiry conversion |
| **Needs a decision** | Pending escalations, with severity and a Review link |
| **Resolved** | Approve / reject / defer history |
| **Notification channels** | Which channels are live, with masked credentials and thresholds |
| **Worker** | What the background worker would send right now (dry run) |
| **Recent leads** | Latest inquiries with estimated pipeline value |
| **AI dashboard** | Links to `/dashboard` for the three agent tabs |

Traffic is captured server-side with no cookies or third-party scripts: every
storefront and product-page view appends an event (`traffic.py`), and referrers are
grouped by host with `www.` normalised away so one source never splits into two
buckets. The event log is capped at 5,000 entries.

### Sales and accounting pipelines

The Sales AI drafts outreach the moment an inquiry arrives, and leads carry an
estimated annual value so the pipeline can be ranked. The Accounting AI reconciles
each report and escalates anomalies. Both pipelines are visible in the panel above.

### The quotation pipeline

A quotation or demo request runs through four agents, in order, and the whole
conversation is kept on the quotation so anyone can see who decided what.

| Stage | Agent | What it does |
|---|---|---|
| 1 | **Marketing AI** | Qualifies the lead — audience, urgency, budget signal |
| 2 | **Sales AI** | Prices the deal: line items, seats, term, discount, cover note |
| 3 | **Accounting AI** | Checks margin and discount; escalates a pricing breach for approval |
| 4 | **Delivery** | E-mails the finished quotation to the customer |

`orchestrator.run_quotation_pipeline()` returns a status plus the transcript:

| Status | Meaning |
|---|---|
| `sent` | E-mailed to the customer |
| `approved_not_sent` | Built and approved, but e-mail was not requested |
| `needs_approval` | A pricing rule was breached — a human must approve before sending |
| `no_email` | No address supplied |
| `failed` | Delivery raised; the quotation is still stored |

Entry points: the **"Request a quotation or demo"** form on every product page, the
JSON API below, or `orchestrator` directly. Get the rendered quote back at
`GET /quotations/{id}`.

### Payment terms

Because deployments are on-premise or offline, billing is **50% on approval of the
quotation, 50% after implementation completes, plus 30% of the contract value for the
annual maintenance fee.** The two instalments exactly reconstruct the contract value;
the retainer sits on top and is billed annually from go-live.

| Item | Default | Env var |
|---|:--:|---|
| Down payment, on approval | 50% | `QUOTE_DOWN_PAYMENT_PCT` |
| Balance, after implementation | 50% | `QUOTE_ON_IMPLEMENTATION_PCT` |
| Annual maintenance retainer | 30% of contract value | `QUOTE_MAINTENANCE_PCT` |
| VAT (included in prices) | 12% | `QUOTE_VAT_RATE` |
| Quotation validity | 30 days | `QUOTE_VALIDITY_DAYS` |
| Gross-margin floor | 45% | `QUOTE_MARGIN_FLOOR_PCT` |
| Discount needing approval | 15% | `QUOTE_DISCOUNT_APPROVAL_PCT` |

Money is `Decimal`, quantised to cents. Prices are quoted **VAT-inclusive**, and
`quotation.gross_margin()` measures margin on year-one revenue.

---

## 6. Control panel security

Accounts live in `users.py`. Passwords are hashed with **PBKDF2-HMAC-SHA256**
(240,000 rounds, per-user random salt) and are never stored or logged in plaintext.

### Roles

| Role | Read escalations | Approve / reject | Manage users | Run worker |
|---|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ |
| `operator` | ✅ | ✅ | ❌ | ✅ |
| `analyst` | ✅ | ❌ | ❌ | ❌ |

**Admins manage accounts at `/control/settings/users`** — create, change role,
enable/disable and reset passwords. The last active administrator cannot be disabled,
demoted or deleted, and you cannot delete your own account.

### Bootstrapping and demo accounts

| Variable | Purpose |
|---|---|
| `CONTROL_PANEL_PASSWORD` | Creates the first `admin` account when no accounts exist. Not a login afterwards. |
| `CONTROL_PANEL_ADMIN_USER` | Username for that bootstrap admin (default `admin`) |
| `SEED_DEMO_USERS` | `true` creates `admin`, `operator`, `analyst` demo accounts |
| `DEMO_USER_PASSWORD` | Shared password for those demo accounts |

Demo seeding runs **before** the bootstrap admin so an enabled demo set is never
shadowed by an admin with a different password.

### Other controls

- **Fails closed**: no accounts → `/api/control/*` returns **503**.
- Signed, `HttpOnly`, `SameSite=lax` session cookie, 8-hour expiry.
- The role is re-read from the store on every request, so disabling a user or changing
  a role takes effect immediately rather than at their next login.
- Passwords compared in constant time; login rate limited to 5 attempts per 5 minutes.
- `GET /api/control/overview` reports channel configuration but **never** returns a
  secret — secrets are masked to their last two characters.

---

## 7. Pushing to GitHub and going live

```bash
# 1. Initialise and commit
git init
git add .
git status                 # confirm .env and var/ are NOT listed
git commit -m "Initial commit: My Team platform"

# 2. Create an empty repository on github.com (no README, no .gitignore)
#    then push:
git branch -M main
git remote add origin https://github.com/mjkulit03/my-team-appstore.git
git push -u origin main
```

`.gitignore` already excludes `.env`, `var/`, caches and virtualenvs. Double-check with
`git status` before committing — the CI workflow fails the build if a `.env` is tracked.

### Publish the app store (free)

After the first push:

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. Run **Actions → Deploy App Store to GitHub Pages → Run workflow** (or push to `main`).
3. The store is live at `https://mjkulit03.github.io/my-team-appstore/`.

If you name the repository differently, the Pages URL follows the repository name.
You can also deploy from a branch instead: **Source → Deploy from a branch → `main` /
`/docs`**. The generated `docs/index.html` is committed, so branch deployment works
without running the build.

> **GitHub Pages cannot run the FastAPI application.** Pages serves static files only.
> The app store is static; the full storefront, quotation pipeline and control panel
> need a Python host (Render, Railway, Fly.io, a VPS, or any machine running
> `uvicorn main:app`). The app store works on its own and links buyers to you directly.

### Add the free secrets

In the repo: **Settings → Secrets and variables → Actions → New repository secret**.

Add each of these as a **secret** (not a variable):

| Secret | Required? | Purpose |
|---|---|---|
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | for email | SMTP relay |
| `NOTIFY_WEBHOOK_URL`, `NOTIFY_WEBHOOK_TOKEN` | for WhatsApp | webhook provider |
| `WORKER_URL`, `WORKER_TOKEN` | optional | point the workflow at a deployed instance |

Add these as **repository variables** (non-secret):

`NOTIFY_ENABLED`, `NOTIFY_CHANNELS`, `SMTP_PORT`, `SMTP_USE_TLS`, `ALERT_EMAILS`,
`NOTIFY_WEBHOOK_PROVIDER`, `NOTIFY_WEBHOOK_PHONE`, `LEAD_VALUE_THRESHOLD`,
`ACCOUNTING_ANOMALY_THRESHOLD`, `CONTROL_PANEL_PASSWORD`, `SESSION_SECRET`.

Generate a session secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> GitHub Actions on public repositories is free for standard hosted runners.
> Scheduled workflows are also free, though GitHub may delay the first runs of a new
> cron job. You can trigger the worker manually any time from the **Actions** tab.

### Workflows

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/ai_background_worker.yml` | every 15 min (`*/15 * * * *`) + manual | Dispatches pending escalations through the notification pipeline. Runs locally if `WORKER_URL` is unset, otherwise POSTs to your deployed instance. Safe on a fresh repo: with no secrets it reports and exits 0. |
| `.github/workflows/ci.yml` | push / pull request | Byte-compiles, runs the test suite, and fails if a `.env` is committed. |
| `.github/workflows/pages.yml` | push to `main` + manual | Rebuilds `docs/index.html` from the catalog and deploys the app store to GitHub Pages. |

---

## 8. API

### Public storefront

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Storefront home (catalog grid) |
| `GET` | `/app-store` | Static app store (also published to GitHub Pages) |
| `GET` | `/products/{slug}` | Product landing page |
| `POST` | `/products/{slug}/inquiry` | Submit a demo request (HTML form) |
| `POST` | `/products/{slug}/quotation` | Request a quotation or demo (HTML form) |
| `GET` | `/api/catalog` | Catalog as JSON |
| `GET` | `/api/products/{slug}` | Product + AI marketing + AI sales copy |
| `GET` | `/api/products/{slug}/campaign` | Draft a campaign (queues approval if needed) |
| `POST` | `/api/products/{slug}/inquiries` | Create an inquiry (JSON) |
| `POST` | `/api/quotations` | Run the pipeline; `product_slug` required in the body |
| `POST` | `/api/products/{slug}/quotation` | Run the pipeline for one product (JSON) |
| `GET` | `/quotations/{id}` | Rendered quotation with payment terms and transcript |
| `POST` | `/api/accounting/report` | Accounting report (escalates anomalies) |

### Agents

| Method | Path |
|---|---|
| `POST` | `/api/agents/marketing` |
| `POST` | `/api/agents/sales` |
| `POST` | `/api/agents/accounting` |

### Control panel (session required)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/control/overview` | Counts, escalation/lead summaries, traffic, channel status |
| `GET` | `/api/control/traffic` | Traffic analysis (`?days=1..90`) |
| `GET` | `/api/control/currency` | Base currency and the conversion table in use |
| `GET` | `/api/control/users` | List accounts and roles (**admin**) |
| `POST` | `/api/control/users` | Create an account (**admin**) |
| `PATCH` | `/api/control/users/{username}` | Change role, name, active flag or password (**admin**) |
| `DELETE` | `/api/control/users/{username}` | Delete an account (**admin**) |
| `GET` | `/api/control/escalations` | List escalations |
| `POST` | `/api/control/escalations/{id}/resolve` | Approve / reject / defer |
| `GET` | `/api/control/leads` | List leads |
| `GET` | `/api/control/quotations` | List quotations and their pipeline statuses |
| `POST` | `/api/control/notify/test` | Send a test alert |
| `POST` | `/api/worker/run` | Run the notification worker now |
| `GET` | `/health` | Liveness (public) |

---

## 9. Project layout

```
agents/                 Marketing, Sales and Accounting rule engines
orchestrator.py         Quotation pipeline: Marketing -> Sales -> Accounting -> email
quotation.py            Line items, VAT, maintenance retainer, payment schedule
api/
  storefront.py         Public catalog + lead APIs
  control.py            Authenticated control-panel APIs
  pages.py              Server-rendered storefront and control-panel pages
auth.py                 Control-panel auth (roles, fail closed, rate limited)
users.py                Role-based accounts + PBKDF2 password hashing
currency.py             PHP base currency, conversion and formatting
catalog/
  products.py           The thirteen products — single source of truth (PHP)
tools/
  build_store.py        Renders docs/index.html (GitHub Pages app store)
docs/
  index.html            Generated static app store (publish root)
  RUNBOOK.md            Operating procedure and troubleshooting
notifications/
  config.py             Environment-variable configuration + masking
  notifier.py           SMTP e-mail and WhatsApp/webhook delivery
  escalations.py        Rules that decide what needs a human
  worker.py             Background worker (CLI + callable)
store.py                JSON persistence for leads, escalations, campaigns, events,
                        quotations
traffic.py              Server-side traffic capture and aggregation
templates/              Jinja2 storefront + control-panel templates
static/                 AI dashboard (index.html/app.js/styles.css) + site.css
docs/RUNBOOK.md         Operating procedure, credentials, troubleshooting
.github/workflows/      ai_background_worker.yml and ci.yml
tests/                  test_agents.py, test_frontend.py, test_platform.py,
                        test_quotation.py, test_users_currency.py
.env.example            Configuration template, no secrets
```

---

## 10. Notes and limits

- The AI employees are **simulated**. Output is templated and derived from the catalog,
  not generated by a language model. Copy reads as competent boilerplate.
- Category and audience detection is keyword matching with a confident fallback to
  `general business`.
- **Persistence is a JSON file** (`DATA_DIR`, default `var/`) guarded by an in-process
  lock. That is fine for a single instance and for GitHub Actions; swap `store.py` for a
  database before running multiple instances or under real load.
- **Traffic analytics are first-party and coarse**: total and per-product counts,
  referrer hosts, and a daily series. There are no unique visitors, no session
  stitching and no bot filtering, so treat the numbers as directional.
- Leads contain personal data (name, email). There is **no** encryption at rest and no
  retention policy — add both before handling real customer data.
- Product names are guessed from descriptions when not supplied. Set the field explicitly
  for production copy.
- The catalog contains fictional product copy written for this suite. Replace it with
  your real products, pricing and terms before selling anything.
- Escalation thresholds are deliberately conservative defaults. Tune them for your
  business before going live.
- The 50/50 + 30% payment terms assume an on-premise or offline deployment. If you sell
  a hosted or subscription deployment, change the `QUOTE_*` percentages.