# Deploying Tweet Reviewer on Coolify

This Streamlit app runs on Coolify, which handles TLS (Let's Encrypt), domain routing,
and reverse proxying via Traefik. **Nothing the researchers upload or review is stored
on the server** — all data lives in the GitHub repo (`inputs/` for raw uploads, `reviews/`
for reviewed outputs). Per-session working files live on a tmpfs (RAM) mount and are
wiped on every restart.

```
Researcher browser ──HTTPS──▶ Coolify/Traefik (TLS + domain) ──HTTP──▶ Streamlit :8503
                                                                         │ GitHub REST API
                                                                         ▼
                                               DGA-Research/TweetReviewer → inputs/  reviews/
```

## Prerequisites
- A [Coolify](https://coolify.io/) instance running.
- A domain name with an A record pointing at your Coolify server (for HTTPS).
- A GitHub **fine-grained Personal Access Token** scoped to **only this repo** with
  **Contents: Read and write**.

## 1. Create a Coolify resource
1. Log into the Coolify dashboard.
2. **New Resource → Docker Compose**
3. Point to the GitHub repository: `DGA-Research/TweetReviewer`, branch `feature/Tweet-Reviewer-VPS`
4. Coolify auto-detects `docker-compose.yml`

## 2. Set environment variables
In Coolify's **Environment Variables** tab, add:

| Key | Value |
|-----|-------|
| `GITHUB_TOKEN` | `github_pat_xxx` |
| `GITHUB_OWNER` | `DGA-Research` |
| `GITHUB_REPO` | `TweetReviewer` |
| `GITHUB_BRANCH` | `feature/Tweet-Reviewer-VPS` (deploy branch — code only) |
| `GITHUB_DATA_BRANCH` | `review-data` (**must differ from `GITHUB_BRANCH`**) |
| `GITHUB_INPUTS_DIR` | `inputs` |
| `GITHUB_REVIEWS_DIR` | `reviews` |
| `STREAMLIT_PASSWORD` | (your shared team password) |

> **Do not point `GITHUB_DATA_BRANCH` at the deploy branch while Auto Deploy is on.**
> The app commits reviewed workbooks every 20 actions. If those commits land on the
> branch Coolify watches, every auto-push fires the deploy webhook and rebuilds the
> container *while people are reviewing* — everyone is thrown back to the password
> screen and their in-RAM progress is wiped. Keeping data on its own branch is what
> prevents this. The branch is created automatically off `GITHUB_BRANCH` on first use,
> so existing files under `inputs/` and `reviews/` carry over and stay loadable.

## 3. Configure the domain
In Coolify's service settings:
- Set your **domain** (e.g. `tweets.example.org`)
- Set **port** to `8503`
- Coolify auto-provisions TLS and routes traffic

## 4. Deploy
Hit **Deploy** in Coolify. It builds and starts the container. 

Enable **Auto Deploy** (webhook) if you want Coolify to redeploy on pushes to the branch.
Safe to leave on **only** if `GITHUB_DATA_BRANCH` differs from `GITHUB_BRANCH` (see the
warning in step 2) — otherwise the app redeploys itself every 20 review actions.

## 5. Daily use (researchers)
- Visit `https://<your-domain>/`
- Log in with the `STREAMLIT_PASSWORD`
- **Upload** a `.xlsx` or `.csv` in the sidebar to start reviewing.
- Click **"Save input to GitHub (inputs/)"** to store the raw file in the repo so it can
  be reopened later from any machine.
- Reviewed output auto-pushes to `reviews/` every 20 actions; **"Push xlsx to Git"** pushes
  on demand.
- Use **"Load from GitHub"** to reopen any previously stored input or review.
- Refreshing the page does not lose progress: the tab's URL carries a session id
  (`?s=...`) and reloading it restores the review. Tell researchers to keep the tab —
  a brand-new tab without that id starts a fresh session. Progress is still only
  *durable* once auto-pushed to GitHub, since working files are in RAM.

## 6. Update the app
Push to `feature/Tweet-Reviewer-VPS` branch; if Auto Deploy is enabled, Coolify redeploys
automatically. Or manually trigger a redeploy in the Coolify dashboard.

## 7. Logs / troubleshooting
In Coolify's dashboard, view **Logs** to see stdout/stderr. Working files (tmpfs) are
wiped on restart; GitHub data is permanent. A restart therefore ends any in-progress
sessions — researchers recover by loading their latest `_autoPush` file from
**"Load from GitHub"**, so prefer restarting outside review hours.

Session working files sit in RAM (a few MB each) and idle ones are swept after
`SESSION_TTL_HOURS` (default 72). Lower it if RAM is tight; set it to `0` to disable
sweeping.

## Local testing
```bash
cp .env.example .env
# Fill in GITHUB_* and STREAMLIT_PASSWORD
docker compose up --build
# Open http://localhost:8503/
```

## Notes
- Use a fine-grained token limited to this single repo; it has write access, so the
  `STREAMLIT_PASSWORD` gate is what keeps it private.
- GitHub authenticated API limit is 5,000 requests/hour — well above this app's usage.
- Coolify's Traefik also works with other platforms (any Docker host); the setup above
  is just the Coolify-specific steps.
