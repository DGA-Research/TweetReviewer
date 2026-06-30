# Tweet Reviewer

Streamlit app for reviewing downloaded tweet spreadsheets. The interface lets you step through tweets, mark each as a simple pass or as a bullet-worthy item, and automatically build a Word clipbook and updated Excel workbook as you go. All data lives in GitHub; nothing is stored on the server.

## Features
- Load `.xlsx` or `.csv` files via upload or from GitHub storage.
- Filter and sort tweets, removing rows without URLs.
- Sidebar metrics plus quick actions for download, manual export, and reset.
- Automatic `.docx` generation that groups bullet tweets under uppercase topics with live hyperlinks.
- **GitHub integration**: reviewed outputs auto-push to `reviews/` every 20 actions; raw inputs can be stored in `inputs/` for later access from any session.
- Per-session isolation: concurrent researchers don't interfere with each other's working files.

## Deployment (Coolify)

See [DEPLOY.md](DEPLOY.md) for step-by-step Coolify setup.

**Quick summary:**
1. Create a Docker Compose resource pointing to this repo, branch `feature/Tweet-Reviewer-VPS`.
2. Set environment variables: `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_BRANCH`, `GITHUB_INPUTS_DIR`, `GITHUB_REVIEWS_DIR`, and optionally `STREAMLIT_PASSWORD`.
3. Configure domain and port (8503); Coolify handles HTTPS via Let's Encrypt.
4. Deploy. Researchers log in with the password (if set) and review tweets.

## Local Development

### Requirements
- Python 3.9+
- Packages: `pip install -r requirements.txt`
- GitHub fine-grained PAT for the repo (Contents: read/write)

### Installation
```bash
git clone -b feature/Tweet-Reviewer-VPS https://github.com/DGA-Research/TweetReviewer.git
cd TweetReviewer
cp .env.example .env
# Edit .env with GitHub credentials and optional STREAMLIT_PASSWORD
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8503/`. If `STREAMLIT_PASSWORD` is set, log in first.

## Workflow

### 1. Load Data
- **Upload**: Click the uploader in the sidebar to add a `.xlsx` or `.csv` file.
- **GitHub picker**: Expand "Load from GitHub" to reopen any previously stored file from `inputs/` or `reviews/`.
- The app removes rows without URLs and sorts by the date column if available.

### 2. Review Tweets
- Read the tweet content, optional flags, and any quote indicators.
- Choose **Pass** for non-actionable tweets or **Bullet** to log them under a topic. Enter a new topic or select a previous one; topics are stored in uppercase.
- Use **Undo last** to revert the most recent action.

### 3. Track Progress
- Sidebar metrics show the counts of passed and bulleted tweets, plus total reviewed.
- Every 20 actions, the app writes your progress to GitHub (`reviews/REVIEWED_...xlsx`) and refreshes the Word clipbook.

### 4. Export & Store
- **Download buttons**: Get the current workbook and Word clipbook.
- **Push xlsx to Git**: Upload on demand to `reviews/`.
- **Save input to GitHub**: Store the raw uploaded file in `inputs/` so it can be reopened later from any machine/session.

## File Naming Convention

Reviewed exports are named `REVIEWED_[handle]_[first_date]_[last_reviewed_date]_[today].xlsx` where:
- `[handle]` is extracted from the tweet URL (e.g. `RandyFeenstra`).
- Dates are in `YYYYMMDD` format.

Auto-pushed files append `_autoPush` before the extension; older auto-push files are pruned on each push.

## GitHub Configuration

Set these as environment variables (Coolify panel) or in `.env` (local):

| Var | Purpose |
|-----|---------|
| `GITHUB_TOKEN` | Fine-grained PAT (this repo, Contents r/w) |
| `GITHUB_OWNER` | Repo owner (e.g. `DGA-Research`) |
| `GITHUB_REPO` | Repo name (e.g. `TweetReviewer`) |
| `GITHUB_BRANCH` | Branch (e.g. `feature/Tweet-Reviewer-VPS`) |
| `GITHUB_INPUTS_DIR` | Folder for raw uploads (default: `inputs`) |
| `GITHUB_REVIEWS_DIR` | Folder for reviewed outputs (default: `reviews`) |
| `STREAMLIT_PASSWORD` | (Optional) Shared app password |

## Resetting for a Fresh Review
- The sidebar warns when existing review marks are detected.
- Select **Reset for re-review** to clear `Reviewed` and `Bullet topic` columns, wipe prior bullet content, and restart from the first tweet. Download a copy first if you need to preserve the original annotations.

## Troubleshooting
- **GitHub not configured**: Set environment variables; the app won't list GitHub files until they're all present.
- **Workbook not detected**: Verify the file extension is `.xlsx` or `.csv` and that it's uploaded or stored on GitHub.
- **Missing columns**: The app expects a `URL` column; add it to your workbook before loading.
- **Password prompt**: If `STREAMLIT_PASSWORD` is set and you see a login screen on first visit, use the configured password.
