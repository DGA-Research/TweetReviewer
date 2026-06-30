# Deploying Tweet Reviewer on a VPS

This runs the Streamlit app behind a [Caddy](https://caddyserver.com/) reverse proxy
that provides automatic HTTPS and HTTP basic auth. **Nothing the researchers upload or
review is stored on the VPS** — all data lives in the GitHub repo (`inputs/` for raw
uploads, `reviews/` for reviewed outputs). Per-session working files live on a tmpfs
(RAM) mount and are wiped on every restart.

```
Researcher browser ──HTTPS──▶ Caddy (TLS + basic auth) ──HTTP──▶ Streamlit app :8501
                                                                    │ GitHub REST API
                                                                    ▼
                                              DGA-Research/TweetReviewer → inputs/  reviews/
```

## Prerequisites
- A VPS with Docker + Docker Compose installed.
- A domain name with an A record pointing at the VPS IP (needed for HTTPS).
- A GitHub **fine-grained Personal Access Token** scoped to **only this repo** with
  **Contents: Read and write**.

## 1. Clone and configure
```bash
git clone -b feature/Tweet-Reviewer-VPS https://github.com/DGA-Research/TweetReviewer.git
cd TweetReviewer
cp .env.example .env
```

Generate the basic-auth password hash:
```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'choose-a-strong-password'
```

Edit `.env` and fill in:
- `DOMAIN` — your public hostname (e.g. `tweets.example.org`).
- `BASIC_AUTH_USER` / `BASIC_AUTH_HASH` — shared team login + the hash from above.
- `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_BRANCH`.
- `GITHUB_INPUTS_DIR` (default `inputs`) and `GITHUB_REVIEWS_DIR` (default `reviews`).

## 2. Launch
```bash
docker compose up -d --build
```
Caddy obtains a TLS certificate automatically on first request. Visit
`https://<DOMAIN>/`, log in with the basic-auth credentials, and the app loads.

## 3. Daily use (researchers)
- **Upload** a `.xlsx` or `.csv` in the sidebar to start reviewing.
- Click **"Save input to GitHub (inputs/)"** to store the raw file in the repo so it can
  be reopened later from any machine.
- Reviewed output auto-pushes to `reviews/` every 20 actions; **"Push xlsx to Git"** pushes
  on demand.
- Use **"Load from GitHub"** to reopen any previously stored input or review.

## 4. Updating the app
```bash
git pull
docker compose up -d --build
```

## 5. Logs / restart
```bash
docker compose logs -f app      # app logs
docker compose logs -f caddy    # TLS / proxy logs
docker compose restart app      # working files are wiped (tmpfs); GitHub data is safe
```

## Local testing (no domain)
Set `DOMAIN=localhost` in `.env`, then `docker compose up --build` and open
`https://localhost/` (accept the local self-signed certificate). The app port 8501 is
intentionally **not** published to the host — all traffic goes through Caddy.

## Notes
- Use a fine-grained token limited to this single repo; it has write access, so the
  basic-auth gate in front of the app is what keeps it private.
- GitHub authenticated API limit is 5,000 requests/hour — well above this app's usage.
