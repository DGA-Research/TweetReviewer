# Tweet Reviewer

Streamlit app for reviewing downloaded tweet spreadsheets. The interface lets you step through tweets, mark each as a simple pass or as a bullet-worthy item, and automatically build a Word clipbook and updated Excel workbook as you go. Progress is auto-saved and can be pushed to GitHub on demand.

## Features
- Filter and sort tweets from Excel workbooks, removing rows without URLs.
- Sidebar metrics plus quick actions for download, manual export, and reset.
- Keyboard shortcuts (`q` for Pass, `w` for Bullet) to speed up triage.
- Automatic `.docx` generation that groups bullet tweets under uppercase topics with live hyperlinks.
- Optional GitHub integration that commits the reviewed sheet every 20 actions and prunes older uploads.

## Virtual Access
- App can be accessed virtually via: https://twitter-review-9frydnk5tqlcgj4zravzuw.streamlit.app/

## Local Requirements (optional)
- Python 3.9 or newer.
- Packages listed in `requirements.txt`.
- Excel workbook (`.xlsx`) with at least the following columns:
  - `URL` (required; rows without a URL are skipped)
  - `Text`
  - `Date` or `Date Correct Format` (used for ordering and exports)
  - Optional columns such as `Reviewed`, `Bullet topic`, `bad_words_found`, `is_quote_tweet`, etc., will be filled or displayed when present.

## Local Installation (optional)
1. (Recommended) Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Place the Excel workbooks you plan to review in the project root alongside `app.py`, or prepare to upload a workbook through the UI.

## Locally Run the App (optional)
Launch Streamlit from the project directory:
```bash
streamlit run app.py
```
Streamlit will open (or display) a local URL such as `http://localhost:8501`. Keep the terminal running while you review tweets.

## Workflow Overview
1. **Load data**
   - Upload a workbook with the sidebar uploader, or pick one of the `.xlsx` files found in the project directory.
   - The app removes rows without URLs and sorts by the date column if available.
2. **Review tweets**
   - Read the tweet content, optional flags, and any quote indicators.
   - Choose **Pass** for non-actionable tweets or **Bullet** to log them under a topic. Enter a new topic or select a previous one; topics are stored in uppercase.
   - Use **Undo last** to revert the most recent action.
3. **Track progress**
   - Sidebar metrics show the counts of passed and bulleted tweets, along with total reviewed.
   - Every 20 actions (`SAVE_INTERVAL`), the app writes your progress back to the Excel workbook and refreshes the Word document (`Issue Clipbook.docx`).

## Exporting Results
- The sidebar includes:
  - Download buttons for the updated workbook and the generated Word clipbook.
  - An editable file name for exports. Changing the name affects both manual and automatic saves.
  - A **Push xlsx to Git** button that uploads the current sheet to GitHub using the configuration described below.
- Bullet entries are rendered into the Word document as quoted text with hyperlinks formatted as `[X, @RandyFeenstra, MM/DD/YY]`.

## GitHub Auto-Push (Optional)
When GitHub secrets are configured, the app will push the reviewed workbook automatically every 20 actions, appending `_autoPush` to the filename. Older auto-push files (and older manual reviews for the same dataset) are removed to avoid clutter.

Create `.streamlit/secrets.toml` with the following structure:
```toml
[github]
token = "ghp_your_personal_access_token"
owner = "your-github-username-or-org"
repo = "your-repo-name"
branch = "main"            # optional; defaults to main
target_dir = "reviews"     # optional subdirectory inside the repo
```
The token must have `repo` scope (or finer-grained equivalent) for the target repository.

## Resetting for a Fresh Review
- The sidebar warns when existing review marks are detected.
- Select **Reset for re-review** to clear `Reviewed` and `Bullet topic` columns, wipe prior bullet content, and restart from the first tweet. The previous Excel backup is overwritten, so download a copy first if you need to preserve the original annotations.

## Troubleshooting
- **Streamlit secrets unavailable**: Ensure you have the `.streamlit/secrets.toml` file in the working directory before launching Streamlit.
- **Workbook not detected**: Verify the file extension is `.xlsx` and that it resides in the same directory as `app.py` (or upload it through the app).
- **Missing columns**: The app expects a `URL` column; add it to your workbook before loading.
