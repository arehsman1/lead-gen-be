# Deploying CalebReview to a VPS

Two paths depending on whether you have a domain pointed at the VPS yet:

## Option A — No domain yet (access via IP:port/lead-gen)

If you haven't pointed a domain at this VPS, skip nginx and certbot
entirely for now — just run the frontend directly on a port and access
it at `http://YOUR_VPS_IP:3000/lead-gen`. The app is built with a
`/lead-gen` path prefix baked in (`NEXT_PUBLIC_BASE_PATH` in
`.env.local.example`) specifically for this case.

Do steps 1, 2, 4, 5, 6, 7, 10, 11, 12 below (skip 3's nginx firewall
rule if you're not running nginx yet, skip 8 nginx and 9 certbot
entirely). Then: `http://YOUR_VPS_IP:8000` for the API,
`http://YOUR_VPS_IP:3000/lead-gen` for the dashboard. Open port 3000 in
the firewall (`sudo ufw allow 3000`) since nginx isn't fronting it.

**One critical gotcha**: `NEXT_PUBLIC_BASE_PATH` (and every other
`NEXT_PUBLIC_*` var) gets baked into the build at `npm run build` time,
not read fresh at runtime. `.env.local` must exist with the right values
*before* you build — if you change it later, you must rebuild
(`npm run build` again), not just restart the service. This tripped me
up once while testing this exact setup — worth flagging so it doesn't
trip you up too.

When you later get a domain, switch to Option B: set
`NEXT_PUBLIC_BASE_PATH=` (empty) in `.env.local`, rebuild, then follow
the nginx/certbot steps below.

## Option B — You have a domain

Assumes a fresh Ubuntu 22.04/24.04 VPS (DigitalOcean, Hetzner, Linode, etc.)
and that you already have:
- Two domains/subdomains pointed at the VPS's IP (A records), e.g.
  `app.calebreview.com` and `api.calebreview.com`
- A Supabase project with `supabase/schema.sql` already applied (see the
  backend README if not)
- GitHub repos for both `caleb-backend` and `caleb-lead-dashboard`

Total first-time setup: roughly 30-45 minutes.

---

## 1. Initial server setup

SSH in as root, then create a non-root user to run everything as (running
production services as root is worth avoiding):

```bash
adduser caleb
usermod -aG sudo caleb
su - caleb
```

From here on, everything runs as `caleb`.

## 2. Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y

# Python 3.12 + venv
sudo apt install -y python3.12 python3.12-venv python3-pip

# Node.js 20 (via NodeSource — Ubuntu's default apt version is too old)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# nginx + certbot for the reverse proxy and SSL
sudo apt install -y nginx certbot python3-certbot-nginx

# git
sudo apt install -y git
```

## 3. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Only nginx (80/443) and SSH are exposed publicly — the backend (8000) and
frontend (3000) only listen on `127.0.0.1`, per the systemd unit files, so
they're unreachable directly from the internet even without this rule,
but it's defense in depth.

## 4. Clone and set up the backend

```bash
cd ~
git clone <your-caleb-backend-repo-url> caleb-backend
cd caleb-backend

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
            # (DEFAULT_USER_ID comes later, in step 11)
            # set CORS_ORIGINS=https://app.calebreview.com
```

Quick sanity check before wiring up systemd:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
curl http://127.0.0.1:8000/health   # should return {"status":"ok"}
kill %1
```

## 5. Set up the backend as a systemd service

```bash
sudo cp deploy/caleb-backend.service /etc/systemd/system/
sudo nano /etc/systemd/system/caleb-backend.service
# Update User/Group/WorkingDirectory/EnvironmentFile/ReadWritePaths if your
# username or paths differ from "caleb" / "/home/caleb/caleb-backend"

sudo systemctl daemon-reload
sudo systemctl enable caleb-backend
sudo systemctl start caleb-backend
sudo systemctl status caleb-backend   # should show "active (running)"
```

## 6. Clone and set up the frontend

```bash
cd ~
git clone <your-caleb-lead-dashboard-repo-url> caleb-lead-dashboard
cd caleb-lead-dashboard

npm ci

cp .env.local.example .env.local
nano .env.local   # NEXT_PUBLIC_API_URL=https://api.calebreview.com

npm run build
```

**Note:** this project does not use `output: "standalone"` in
`next.config.ts` on purpose — `next start` serves `.next/static` and
`public/` directly from the project directory with no extra step,
avoiding a real bug standalone mode has: it requires manually copying
`.next/static` into `.next/standalone/.next/static` after every single
rebuild, and if that copy is ever forgotten (e.g. after a later
`git pull` + rebuild), the page loads with broken/missing CSS — the
HTML references new hashed chunk filenames that don't exist in the
stale copied folder. Confirmed by actually reproducing it: built with
standalone mode, skipped the copy, and the CSS `<link>` 404'd. Removing
standalone mode removes the whole failure mode, since this VPS already
runs `npm ci` with full `node_modules` present anyway — the main reason
to use standalone (a slim, dependency-free bundle) doesn't apply here.

Quick sanity check:

```bash
npm run start &
curl -I http://127.0.0.1:3000   # should return HTTP 200 or a redirect to /lead-gen
kill %1
```

## 7. Set up the frontend as a systemd service

```bash
sudo cp deploy/caleb-frontend.service /etc/systemd/system/
sudo nano /etc/systemd/system/caleb-frontend.service
# Same check as step 5 — update paths/user if needed

sudo systemctl daemon-reload
sudo systemctl enable caleb-frontend
sudo systemctl start caleb-frontend
sudo systemctl status caleb-frontend
```

## 8. nginx reverse proxy

```bash
sudo cp caleb-review.conf /etc/nginx/sites-available/caleb-review.conf
sudo nano /etc/nginx/sites-available/caleb-review.conf
# Confirm server_name lines match your actual domains

sudo ln -s /etc/nginx/sites-available/caleb-review.conf /etc/nginx/sites-enabled/
sudo nginx -t          # test config syntax before reloading
sudo systemctl reload nginx
```

At this point `http://app.calebreview.com` and `http://api.calebreview.com/health`
should both work over plain HTTP.

## 9. SSL (HTTPS)

```bash
sudo certbot --nginx -d app.calebreview.com -d api.calebreview.com
```

Certbot edits the nginx config in place to add the SSL server blocks and
redirect HTTP → HTTPS, and sets up auto-renewal via a systemd timer
(`sudo systemctl status certbot.timer` to confirm). No further action
needed — certs renew themselves.

**After this, update two things to use https://**
- Backend `.env`: `CORS_ORIGINS=https://app.calebreview.com`
- Frontend `.env.local`: `NEXT_PUBLIC_API_URL=https://api.calebreview.com`

Then restart both services:
```bash
sudo systemctl restart caleb-backend caleb-frontend
```

## 10. Create your Supabase Storage bucket

If you haven't already: Supabase dashboard → Storage → New bucket →
name it `audit-pdfs`, uncheck "Public".

## 11. Create your one user row

There's no login system — see the backend README for why. Run the
one-time SQL at the bottom of `supabase/schema.sql` (Supabase dashboard →
SQL Editor) to create your single user + settings row, then copy the
returned `id` into `DEFAULT_USER_ID` in the backend's `.env` and restart
it: `sudo systemctl restart caleb-backend`. Then just open
`https://app.calebreview.com` (or `http://YOUR_IP:3000/lead-gen`) —
no login screen, it goes straight to the dashboard.

## 12. Set up PDF cleanup (optional but recommended)

Generated PDFs are deleted automatically after `PDF_RETENTION_DAYS`
(default 14 — change it in the backend's `.env`) via a script, but
nothing runs that script unless you schedule it. Add to the backend
user's crontab (`crontab -e`):

```
0 3 * * * cd /home/caleb/caleb-backend && .venv/bin/python -m app.scripts.cleanup_expired_pdfs >> /var/log/caleb-pdf-cleanup.log 2>&1
```

Runs daily at 3am. Test it manually first:

```bash
cd ~/caleb-backend && .venv/bin/python -m app.scripts.cleanup_expired_pdfs
```

---

## Redeploying after code changes

Each project has a `deploy/redeploy.sh` script:

```bash
# Backend
cd ~/caleb-backend && ./deploy/redeploy.sh

# Frontend
cd ~/caleb-lead-dashboard && ./deploy/redeploy.sh
```

Both scripts: pull latest → install deps → build (frontend only) →
restart the systemd service → hit the health endpoint to confirm it came
back up. If the health check fails, both scripts point you at
`journalctl` to see why.

Make them executable once: `chmod +x deploy/redeploy.sh` in each repo.

## Checking logs

```bash
sudo journalctl -u caleb-backend -f      # live tail
sudo journalctl -u caleb-frontend -f
sudo journalctl -u caleb-backend -n 100  # last 100 lines
```

## Common issues

- **502 Bad Gateway from nginx** — the backend/frontend service isn't
  running. Check `systemctl status caleb-backend` /
  `caleb-frontend` and the journalctl logs above.
- **CORS errors in the browser console** — `CORS_ORIGINS` in the backend
  `.env` doesn't match the frontend's actual URL exactly (including
  https://, no trailing slash). Restart the backend after changing it.
- **500 errors mentioning Supabase/database on every request** — check
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `DEFAULT_USER_ID` in
  the backend's `.env` are correct and that you ran the one-time SQL to
  create your user row (step 11).
- **PDF/audit requests time out** — the nginx config already extends the
  proxy timeout to 120s for the API server block; if audits are timing
  out beyond that (e.g. very slow target websites), increase
  `proxy_read_timeout` further in `caleb-review.conf`.
