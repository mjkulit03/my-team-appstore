# Runbook — My Team Platform

Operating procedure: how to install, run, sign in, manage users and recover.
Everything here is free and runs on a single machine.

---

## 1. Requirements

| Need | Notes |
|---|---|
| Python 3.11+ | 3.12 recommended |
| pip | ships with Python |
| ~40 MB disk | no database, no bundler |
| Network | none required at runtime |

There is no LLM key, no paid service and no external database.

---

## 2. First-time setup (5 minutes)

```bash
cd "C:/Users/jmanahan/Videos/My Team"

pip install -r requirements.txt

cp .env.example .env      # Windows Git Bash: cp .env.example .env
```

Open `.env` in a text editor and set at least one password so you can sign in:

```bash
CONTROL_PANEL_PASSWORD=choose-a-long-password
SESSION_SECRET=paste-something-random-here
```

Generate a good session secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Optional: turn on the demo accounts

```bash
SEED_DEMO_USERS=true
DEMO_USER_PASSWORD=demo-pass-2024
```

These three accounts are created **only** when `SEED_DEMO_USERS=true` and share the
`DEMO_USER_PASSWORD` you chose. See §5 for the credentials.

---

## 3. Run it

```bash
uvicorn main:app --reload --port 8000
```

Then open:

| URL | What it is |
|---|---|
| http://127.0.0.1:8000/ | Storefront — 8 products, pricing in PHP (₱) |
| http://127.0.0.1:8000/dashboard | AI Command Center (Marketing / Sales / Accounting) |
| http://127.0.0.1:8000/control/login | Control panel sign-in |
| http://127.0.0.1:8000/control/settings/users | User accounts (admin only) |
| http://127.0.0.1:8000/docs | Interactive API docs |

Use `--reload` while developing; drop it for a normal run.

### Run the tests

```bash
python -m pytest
```

Expected: the suite reports **all tests passing** and exits with status 0. Any
failure or error means something regressed — fix it before continuing.

---

## 4. Signing in

The **storefront and AI dashboard are public** — no sign-in needed.

The **control panel** needs an account:

1. Go to http://127.0.0.1:8000/control/login
2. Sign in with a username and password
3. You land on `/control/overview`

### If you are locked out

If you set `CONTROL_PANEL_PASSWORD` before any accounts existed, an `admin` account is
created automatically at startup using that password:

```
username: admin
password: the value of CONTROL_PANEL_PASSWORD
```

If accounts already exist, `CONTROL_PANEL_PASSWORD` is **not** a login. Sign in as an
existing admin instead. If every account is lost, stop the server, delete the runtime
data and restart — a fresh `admin` will be bootstrapped:

```bash
# stop the server first (Ctrl+C), then:
rm -rf var          # Windows Git Bash
python -m uvicorn main:app --port 8000
```

> `var/` holds leads, escalations, campaigns, traffic events and user accounts.
> Deleting it resets the platform. Back it up if you need the data.

---

## 5. Demo credentials

Created only when `SEED_DEMO_USERS=true` and `DEMO_USER_PASSWORD` is set.

| Username | Role | What they can do |
|---|---|---|
| `admin` | Administrator | Everything, including creating and disabling users |
| `operator` | Operator | Approve/reject escalations, resolve alerts, view leads |
| `analyst` | Analyst (read-only) | View dashboards, traffic and pipelines only |

The password for all three is whatever you set in `DEMO_USER_PASSWORD`
(the example above uses `demo-pass-2024`).

**Change or remove these before exposing the app to the internet.** Demo accounts share
one password; they are for demonstrations and local review, not production.

### Roles in detail

| Role | Read escalations | Approve / reject | Manage users | Run worker |
|---|:--:|:--:|:--:|:--:|
| `admin` | ✅ | ✅ | ✅ | ✅ |
| `operator` | ✅ | ✅ | ❌ | ✅ |
| `analyst` | ✅ | ❌ | ❌ | ❌ |

The system will not let you disable, demote or delete the **last active administrator**.

---

## 6. Managing users (admin only)

1. Sign in as `admin`
2. Go to **User accounts** at http://127.0.0.1:8000/control/settings/users
3. Use **Create an account** — username, full name, password (8+ chars), role
4. The accounts table lets you change a role or disable/enable an account
5. **Reset a password** replaces the password for any account

Username rules: 3–32 characters, lowercase letters, numbers, `.`, `-` or `_`.

Passwords are hashed with PBKDF2-HMAC-SHA256 (240,000 rounds) and are never shown again
— if you lose one, reset it from this page rather than trying to read it.

### Adding someone by hand

```bash
python -c "
import users
users.create_user('maria', 'her-temp-password', 'operator', 'Maria Reyes')
print('created')"
```

---

## 7. Currency

Prices are in **Philippine peso (PHP)** with a USD equivalent shown alongside.

| Variable | Default | Purpose |
|---|---|---|
| `BASE_CURRENCY` | `PHP` | Currency the platform prices in |
| `FX_USD` | `0.0165` | Rate per 1 PHP. Also `FX_EUR`, `FX_GBP`, `FX_JPY`, … |

Rates are indicative and static — no FX API is called, so the platform stays free,
fast and deterministic. Update `FX_*` when you want fresher figures:

```bash
FX_USD=0.0168
```

Check the active table at any time:

```bash
curl http://127.0.0.1:8000/api/control/currency -b cookies.txt
```

The Accounting agent accepts any of `PHP, USD, EUR, GBP, JPY, SGD, HKD, AUD, CAD, AED`
in its `currency` field.

---

## 8. Notifications

Off by default. To send email alerts:

```bash
NOTIFY_ENABLED=true
NOTIFY_CHANNELS=email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-google-app-password     # App Password, not your account password
SMTP_FROM=you@gmail.com
ALERT_EMAILS=ops@yourcompany.com
```

For WhatsApp (CallMeBot example):

```bash
NOTIFY_CHANNELS=whatsapp
NOTIFY_WEBHOOK_PROVIDER=callmebot
NOTIFY_WEBHOOK_URL=https://api.callmebot.com/whatsapp.php
NOTIFY_WEBHOOK_TOKEN=your-callmebot-apikey
NOTIFY_WEBHOOK_PHONE=15551234567
```

### Test the pipeline

```bash
# See what would be sent, without sending
python -m notifications.worker --dry-run

# Send for real
python -m notifications.worker
```

Escalations are raised for: **campaign approval** (regulated products), **high-value
leads** (default ≥ ₱150,000) and **accounting anomalies** (default net loss ≥ ₱50,000).
Tune with `LEAD_VALUE_THRESHOLD` and `ACCOUNTING_ANOMALY_THRESHOLD`.

---

## 9. Quotations

Every product page has a **"Request a quotation or demo"** form. Submitting it runs the
four-agent pipeline and returns the rendered quotation:

1. **Marketing AI** — qualifies the lead
2. **Sales AI** — builds line items, seats, term, discount, cover note
3. **Accounting AI** — checks margin and discount, escalates a breach
4. **Delivery** — e-mails the quotation

### Payment terms (on-premise / offline deployments)

| When | What | Default |
|---|---|---|
| On approval of the quotation | 50% down payment | `QUOTE_DOWN_PAYMENT_PCT=50` |
| After implementation completes | 50% balance | `QUOTE_ON_IMPLEMENTATION_PCT=50` |
| Annually from go-live | 30% of contract value, maintenance | `QUOTE_MAINTENANCE_PCT=30` |

All prices are **VAT-inclusive** (`QUOTE_VAT_RATE=12`). The two instalments add up to the
contract value exactly; the retainer is on top, so year one is contract + 30%.

### Other quotation settings

| Variable | Default | Purpose |
|---|:--:|---|
| `QUOTE_VALIDITY_DAYS` | 30 | Days the quote stays valid |
| `QUOTE_MARGIN_FLOOR_PCT` | 45 | Below this the Accounting AI escalates |
| `QUOTE_DISCOUNT_APPROVAL_PCT` | 15 | Discount above this needs a human |

### Produce a quotation by hand

```bash
curl -X POST http://127.0.0.1:8000/api/products/clinic-inventory-system/quotation \
  -H 'Content-Type: application/json' \
  -d '{"name":"Ana Reyes","email":"ana@example.com","organisation":"Acme Clinic",
       "seats":12,"term_months":12,"discount_pct":10,"support":true,"send_email":false}'
```

`send_email:false` builds and approves the quote without contacting anyone — the safe way
to try it. The response carries `status`, `quotation`, `quotation_id` and the four-stage
`transcript`.

### Reading the status

| `status` | What to do |
|---|---|
| `sent` | Nothing; it went to the customer |
| `approved_not_sent` | Nothing; you asked not to send |
| `needs_approval` | Approve it in the control panel, then send manually |
| `no_email` | The customer gave no address; quote it by hand |
| `failed` | Delivery raised. The quotation is stored — resend by e-mail |

If `needs_approval`, the breach is on the quotation itself (margin below the floor, or a
discount above the approval threshold), so you can see what to authorise.

---

## 10. Scheduled background runs (GitHub Actions, free)

`.github/workflows/ai_background_worker.yml` runs every 15 minutes.

1. Push the repo to GitHub (see README §7)
2. **Settings → Secrets and variables → Actions** — add the secrets
3. **Actions → AI Background Worker → Run workflow** to trigger it manually once

With no secrets configured the job runs, reports what it would do, and exits 0 — safe to
enable on a fresh repository.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/control/login` says "Control panel disabled" | No accounts exist | Set `CONTROL_PANEL_PASSWORD` (8+ chars) and restart |
| Every password is rejected | Accounts exist; env password is not a login | Sign in as an existing admin |
| `503` from `/api/control/*` | Panel not set up | Same as the first row |
| `401` from `/api/control/*` | Not signed in, or the account was disabled | Sign in again |
| `403` from a control action | Your role lacks permission | Sign in as an `admin` or `operator` |
| "Too many attempts" | Login rate limit (5 per 5 min) | Wait 5 minutes |
| Prices show `$` instead of `₱` | `BASE_CURRENCY` changed | Unset it; default is `PHP` |
| Notifications never arrive | `NOTIFY_ENABLED` not true, or channel unconfigured | Check the Notification channels card on the overview |
| Escalations stuck pending | No channel configured | Configure SMTP or the webhook, then re-run the worker |
| 404 on a product page | Unknown slug | Use `/api/catalog` to list valid slugs |
| Quotation says `needs_approval` | Margin below `QUOTE_MARGIN_FLOOR_PCT` or discount above `QUOTE_DISCOUNT_APPROVAL_PCT` | Read the breach on the quote, then approve or re-price |
| Quotation says `failed` | SMTP rejected the send | Check the SMTP settings and `NOTIFY_ENABLED`; the quote is still stored |
| Quotation says `no_email` | The form had no e-mail address | Re-run with an address, or quote manually |
| A percentage renders as `3E+1` | Decimal formatting regression | Must not happen — `quotation.pct()` is the only formatter allowed in quotes |
| Port already in use | Another process on 8000 | Use `--port 8001` |

### Reset everything (development only)

```bash
# stop the server with Ctrl+C first
rm -rf var
rm -f .env
python -m pytest          # confirm the suite still passes
```

---

## 12. Daily operating notes

- **Approve work**: `/control/overview` → *Needs a decision* → **Review**
- **Check the books**: `/control/accounting` or post entries to `/api/accounting/report`
- **Watch interest**: *Traffic analysis* on the overview shows which products get views
- **Flush alerts**: `python -m notifications.worker`
- **Add staff**: *User accounts* → create, then give the least-privileged role that works

Data lives in `var/store.json`. Back it up before any maintenance.