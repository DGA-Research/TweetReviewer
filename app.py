import os
import re
import base64
from datetime import datetime
from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st
import requests
import streamlit.components.v1 as components
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

WORD_FILENAME = "Issue Clipbook.docx"
SAVE_INTERVAL = 20


def trigger_rerun() -> None:
    rerun_fn = getattr(st, 'experimental_rerun', None) or getattr(st, 'rerun', None)
    if rerun_fn is None:
        raise RuntimeError('Streamlit rerun function is unavailable in this environment.')
    rerun_fn()





def ensure_hotkeys_script() -> None:
    if st.session_state.get("hotkeys_injected"):
        return

    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            if (doc.hotkeysRegistered) { return; }
            doc.hotkeysRegistered = true;
            doc.addEventListener('keydown', function(event) {
                const active = doc.activeElement;
                if (active && ['INPUT', 'TEXTAREA'].includes(active.tagName)) {
                    return;
                }
                const key = event.key.toLowerCase();
                if (key === 'q' || key === 'w') {
                    const label = key === 'q' ? 'Pass (Q)' : 'Bullet (W)';
                    const buttons = Array.from(doc.querySelectorAll('button'));
                    const target = buttons.find(btn => {
                        const text = (btn.innerText || '').trim();
                        return text === label;
                    });
                    if (target) {
                        target.click();
                        event.preventDefault();
                    }
                }
            }, true);
        })();
        </script>
        """,
        height=0,
        width=0,
    )
    st.session_state.hotkeys_injected = True












def extract_handle_from_url(url: str) -> str:
    if not isinstance(url, str):
        return 'unknown'

    match = re.search(r"https?://(?:www\.)?(?:twitter|x)\.com/([^/]+)", url, re.IGNORECASE)
    if not match:
        return 'unknown'

    handle = match.group(1).strip('@').strip()
    return handle or 'unknown'


def derive_export_metadata(df: pd.DataFrame) -> tuple[str, str, str, str]:
    handle = 'unknown'
    url_series = df.get('URL')
    if url_series is not None and not url_series.dropna().empty:
        handle = extract_handle_from_url(url_series.dropna().iloc[0])

    date_series = df.get('Date Correct Format')
    fallback_date_series = df.get('Date')
    first_date = 'unknown'
    last_tweet_date = 'unknown'
    if date_series is None or date_series.dropna().empty:
        date_series = fallback_date_series
    if date_series is not None and not date_series.dropna().empty:
        try:
            dates = pd.to_datetime(date_series.dropna())
            if not dates.empty:
                first_date = dates.min().strftime('%Y%m%d')
                last_tweet_date = dates.max().strftime('%Y%m%d')
        except Exception:
            pass

    last_reviewed_date = 'unknown'
    reviewed_series = df.get('Reviewed')
    if reviewed_series is not None:
        reviewed_mask = reviewed_series.fillna(False).astype(bool)
        if reviewed_mask.any():
            candidate_dates = df.loc[reviewed_mask, 'Date Correct Format'] if 'Date Correct Format' in df.columns else None
            if candidate_dates is None or candidate_dates.dropna().empty:
                candidate_dates = df.loc[reviewed_mask, 'Date'] if 'Date' in df.columns else None
            if candidate_dates is not None and not candidate_dates.dropna().empty:
                try:
                    reviewed_dates = pd.to_datetime(candidate_dates.dropna())
                    if not reviewed_dates.empty:
                        last_reviewed_date = reviewed_dates.max().strftime('%Y%m%d')
                except Exception:
                    pass

    return handle, first_date, last_reviewed_date, last_tweet_date


def build_export_filename(df: pd.DataFrame) -> str:
    handle, first_date, last_reviewed_date, last_tweet_date = derive_export_metadata(df)
    reviewed_series = df.get('Reviewed')
    any_reviewed = False
    if reviewed_series is not None:
        any_reviewed = reviewed_series.fillna(False).astype(bool).any()
    if any_reviewed:
        today = datetime.now().strftime('%Y%m%d')
        parts = ['REVIEWED', handle, first_date, last_reviewed_date, today]
    else:
        parts = ['UNREVIEWED', handle, first_date, last_tweet_date]
    safe_parts = [re.sub(r'[^A-Za-z0-9_-]+', '_', part) if part else 'unknown' for part in parts]
    return '_'.join(safe_parts) + '.xlsx'




def refresh_export_name() -> None:
    if 'df' not in st.session_state:
        return
    previous_auto = st.session_state.get('initial_export_name')
    new_name = build_export_filename(st.session_state.df)
    st.session_state.initial_export_name = new_name
    if 'export_name' not in st.session_state or st.session_state.get('export_name') == previous_auto:
        st.session_state.pending_export_name = new_name



def get_github_config() -> tuple[bool, dict | str]:
    if not hasattr(st, 'secrets'):
        return False, 'Streamlit secrets unavailable; add GitHub credentials to st.secrets'

    cfg = st.secrets.get('github', {})
    token = cfg.get('token')
    owner = cfg.get('owner')
    repo = cfg.get('repo')
    branch = cfg.get('branch', 'main')
    target_dir = (cfg.get('target_dir') or '').strip('/')

    if not token or not owner or not repo:
        return False, 'Streamlit secrets missing github.token, github.owner, or github.repo'

    return True, {
        'token': token,
        'owner': owner,
        'repo': repo,
        'branch': branch,
        'target_dir': target_dir,
    }


def save_and_git_commit(destination: Path, df: pd.DataFrame) -> tuple[bool, str]:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(destination, index=False)
    except Exception as exc:
        return False, f"Failed to save workbook: {exc}"

    try:
        file_bytes = destination.read_bytes()
    except Exception as exc:
        return False, f"Failed to read saved workbook: {exc}"

    ok, cfg_or_message = get_github_config()
    if not ok:
        return False, cfg_or_message

    cfg = cfg_or_message
    encoded_content = base64.b64encode(file_bytes).decode('utf-8')

    relative_path = destination.name if not cfg['target_dir'] else f"{cfg['target_dir']}/{destination.name}"
    url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{relative_path}"
    headers = {
        'Authorization': f"Bearer {cfg['token']}",
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }

    params = {'ref': cfg['branch']}
    existing_sha = None
    get_response = requests.get(url, headers=headers, params=params)
    if get_response.status_code == 200:
        existing_sha = get_response.json().get('sha')
    elif get_response.status_code not in (200, 404):
        return False, f"GitHub API error ({get_response.status_code}): {get_response.text}"

    payload = {
        'message': f"Add reviewed tweets {destination.name}",
        'content': encoded_content,
        'branch': cfg['branch'],
    }
    if existing_sha:
        payload['sha'] = existing_sha

    put_response = requests.put(url, headers=headers, json=payload)
    if put_response.status_code not in (200, 201):
        return False, f"GitHub API error ({put_response.status_code}): {put_response.text}"

    return True, f"Uploaded and committed {destination.name} to GitHub"

def list_excel_files() -> list[str]:
    return sorted([name for name in os.listdir(".") if name.lower().endswith(".xlsx")])


def prepare_document(doc: Document) -> Document:
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(10)
    try:
        heading = doc.styles["Heading 2"]
    except KeyError:
        heading = doc.styles.add_style("Heading 2", WD_STYLE_TYPE.PARAGRAPH)
    heading.font.name = "Arial"
    heading.font.size = Pt(12)
    heading.font.bold = True
    return doc


def load_dataframe(file_path: str) -> tuple[pd.DataFrame, int]:
    df = pd.read_excel(file_path)
    if "URL" not in df.columns:
        raise ValueError("Expected a 'URL' column in the workbook")

    original = len(df)
    df = df[df["URL"].fillna("").str.strip() != ""].reset_index(drop=True)
    removed = original - len(df)

    if 'Date Correct Format' in df.columns:
        sort_series = pd.to_datetime(df['Date Correct Format'], errors='coerce')
    else:
        sort_series = None
    if sort_series is None or sort_series.dropna().empty:
        sort_series = pd.to_datetime(df['Date'], errors='coerce') if 'Date' in df.columns else None
    if sort_series is not None:
        df = df.assign(_sort_date=sort_series).sort_values('_sort_date', kind='stable', na_position='last').drop(columns='_sort_date').reset_index(drop=True)

    if 'Reviewed' not in df.columns:
        df['Reviewed'] = False
    df['Reviewed'] = df['Reviewed'].fillna(False).astype(bool)

    if 'Bullet topic' not in df.columns:
        df['Bullet topic'] = ''
    df['Bullet topic'] = df['Bullet topic'].fillna('').astype(str)

    return df, removed


def initialize_state(file_path: str, source_label: str | None = None) -> None:
    df, removed = load_dataframe(file_path)
    st.session_state.df = df
    st.session_state.excel_path = file_path
    st.session_state.source_label = source_label or Path(file_path).name
    st.session_state.removed_rows = removed
    if removed:
        df.to_excel(file_path, index=False)

    if os.path.exists(WORD_FILENAME):
        doc = Document(WORD_FILENAME)
    else:
        doc = Document()
    st.session_state.doc = prepare_document(doc)

    st.session_state.topic_input = ''
    st.session_state.topic_select = ''
    st.session_state.clear_topic_inputs = False

    st.session_state.content_by_topic: dict[str, list[dict[str, str]]] = {}
    st.session_state.topic_history: list[str] = []
    st.session_state.history_stack: list[dict[str, object]] = []
    st.session_state.current_index = 0
    st.session_state.actions_since_save = 0
    st.session_state.last_save_message = None
    st.session_state.last_export_message = None
    st.session_state.initial_export_name = build_export_filename(df)
    st.session_state.reset_export_name = False
    st.session_state.export_name = st.session_state.initial_export_name
    update_counts()
    refresh_export_name()
    advance_to_next_unreviewed()


def update_counts() -> None:
    df = st.session_state.df
    reviewed = df['Reviewed'].fillna(False).astype(bool) if 'Reviewed' in df.columns else pd.Series(dtype=bool)
    bullet_topics = df['Bullet topic'].fillna('').astype(str).str.strip() if 'Bullet topic' in df.columns else pd.Series([''] * len(df))
    bullet_mask = reviewed & (bullet_topics != '')
    pass_mask = reviewed & ~bullet_mask
    st.session_state.pass_count = int(pass_mask.sum())
    st.session_state.bullet_count = int(bullet_mask.sum())
    st.session_state.total_reviewed = st.session_state.pass_count + st.session_state.bullet_count


def advance_to_next_unreviewed() -> None:
    df = st.session_state.df
    idx = st.session_state.current_index
    while idx < len(df) and bool(df.at[idx, 'Reviewed']):
        idx += 1
    st.session_state.current_index = idx


def save_progress(force: bool = False) -> None:
    if not force and st.session_state.actions_since_save < SAVE_INTERVAL:
        return
    st.session_state.df.to_excel(st.session_state.excel_path, index=False)
    st.session_state.doc.save(WORD_FILENAME)
    st.session_state.actions_since_save = 0
    st.session_state.last_save_message = f"Progress saved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def increment_action_counter() -> None:
    st.session_state.actions_since_save += 1
    save_progress()


def normalize_spaces(text: str) -> str:
    text = re.sub(r"([.?!]) {2,}", r"\\1 ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def add_hyperlink_date_only(paragraph, prefix: str, date_part: str, suffix: str, url: str) -> None:
    run_prefix = paragraph.add_run(prefix)
    run_prefix.font.name = "Arial"
    run_prefix.font.size = Pt(10)

    part = paragraph.part
    rel_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)

    new_run = OxmlElement("w:r")
    run_props = OxmlElement("w:rPr")

    run_style = OxmlElement("w:rStyle")
    run_style.set(qn("w:val"), "Hyperlink")
    run_props.append(run_style)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0000FF")
    run_props.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_props.append(underline)

    new_run.append(run_props)
    text_element = OxmlElement("w:t")
    text_element.text = date_part
    new_run.append(text_element)

    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)

    run_suffix = paragraph.add_run(suffix)
    run_suffix.font.name = "Arial"
    run_suffix.font.size = Pt(10)


def rebuild_document() -> None:
    doc = st.session_state.doc
    content = st.session_state.content_by_topic

    for paragraph in list(doc.paragraphs):
        element = paragraph._element
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)

    for topic in sorted(content.keys()):
        doc.add_paragraph(topic, style="Heading 2")
        for entry in content[topic]:
            para = doc.add_paragraph()
            run = para.add_run(entry["quoted_text"] + " ")
            run.font.name = "Arial"
            run.font.size = Pt(10)
            add_hyperlink_date_only(para, "[X, @RandyFeenstra, ", entry["date_str"], "]", entry["url"])

            doc.add_paragraph()
            centered = doc.add_paragraph()
            centered.alignment = 1
            add_hyperlink_date_only(centered, "[X, @RandyFeenstra, ", entry["date_str"], "]", entry["url"])
            doc.add_paragraph()


def format_text_for_bullet(row: pd.Series, topic: str) -> None:
    text = str(row.get("Text", ""))
    url = str(row.get("URL", ""))
    date_value = row.get("Date Correct Format")
    if pd.isna(date_value):
        date_value = row.get("Date")
    date = pd.to_datetime(date_value)
    date_str = f"{date.month}/{date.day}/{str(date.year)[2:]}"

    text = text.replace('"', "'").replace("\n", "\u00A0")
    text = normalize_spaces(text)
    quoted = f'"{text}"'

    entries = st.session_state.content_by_topic.setdefault(topic, [])
    entries.append({"quoted_text": quoted, "url": url, "date_str": date_str})
    rebuild_document()


def handle_pass() -> None:
    df = st.session_state.df
    idx = st.session_state.current_index
    prev_reviewed = bool(df.at[idx, 'Reviewed']) if 'Reviewed' in df.columns else False
    prev_topic_value = df.at[idx, 'Bullet topic'] if 'Bullet topic' in df.columns else ''
    prev_topic = '' if pd.isna(prev_topic_value) else str(prev_topic_value)
    df.at[idx, 'Reviewed'] = True
    df.at[idx, 'Bullet topic'] = ''
    st.session_state.history_stack.append({
        'index': idx,
        'action': 'pass',
        'prev_reviewed': prev_reviewed,
        'prev_topic': prev_topic,
    })
    st.session_state.current_index += 1
    update_counts()
    refresh_export_name()
    increment_action_counter()
    advance_to_next_unreviewed()


def handle_bullet(topic: str) -> None:
    df = st.session_state.df
    idx = st.session_state.current_index
    topic_clean = topic.strip()
    topic_upper = topic_clean.upper()
    prev_reviewed = bool(df.at[idx, 'Reviewed']) if 'Reviewed' in df.columns else False
    prev_topic_value = df.at[idx, 'Bullet topic'] if 'Bullet topic' in df.columns else ''
    prev_topic = '' if pd.isna(prev_topic_value) else str(prev_topic_value)
    df.at[idx, 'Reviewed'] = True
    df.at[idx, 'Bullet topic'] = topic_clean
    st.session_state.history_stack.append({
        'index': idx,
        'action': 'bullet',
        'prev_reviewed': prev_reviewed,
        'prev_topic': prev_topic,
        'topic': topic_upper,
    })
    format_text_for_bullet(df.iloc[idx], topic_upper)
    if topic_upper not in st.session_state.topic_history:
        st.session_state.topic_history.append(topic_upper)
    st.session_state.current_index += 1
    update_counts()
    refresh_export_name()
    increment_action_counter()
    advance_to_next_unreviewed()


def handle_back() -> bool:
    if not st.session_state.history_stack:
        return False

    entry = st.session_state.history_stack.pop()
    idx = entry.get('index')
    action = entry.get('action')
    topic = entry.get('topic')

    if action == 'bullet' and topic:
        entries = st.session_state.content_by_topic.get(topic, [])
        if entries:
            entries.pop()
            if not entries:
                st.session_state.content_by_topic.pop(topic, None)
        rebuild_document()

    prev_reviewed = entry.get('prev_reviewed', False)
    prev_topic = entry.get('prev_topic', '')
    st.session_state.df.at[idx, 'Reviewed'] = prev_reviewed
    st.session_state.df.at[idx, 'Bullet topic'] = prev_topic

    st.session_state.current_index = idx
    st.session_state.actions_since_save = max(st.session_state.actions_since_save - 1, 0)
    update_counts()
    refresh_export_name()
    advance_to_next_unreviewed()
    return True


def reset_for_rereview() -> None:
    st.session_state.df['Reviewed'] = False
    st.session_state.df['Bullet topic'] = ''
    st.session_state.history_stack = []
    st.session_state.content_by_topic = {}
    st.session_state.topic_history = []
    st.session_state.current_index = 0
    st.session_state.actions_since_save = 0
    st.session_state.clear_topic_inputs = False
    st.session_state.doc = prepare_document(Document())
    st.session_state.last_export_message = None
    st.session_state.initial_export_name = build_export_filename(st.session_state.df)
    st.session_state.reset_export_name = True
    st.session_state.pop('export_name', None)
    update_counts()
    refresh_export_name()
    advance_to_next_unreviewed()
    st.session_state.df.to_excel(st.session_state.excel_path, index=False)
    save_progress(force=True)


def main() -> None:
    st.set_page_config(page_title="Tweet Reviewer", layout="wide")
    st.title("Tweet Reviewer")

    uploaded_file = st.sidebar.file_uploader("Upload Excel workbook", type=["xlsx"])
    if uploaded_file is not None:
        uploaded_bytes = uploaded_file.getvalue()
        file_signature = (uploaded_file.name, len(uploaded_bytes))
        if st.session_state.get("uploaded_file_signature") != file_signature:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(uploaded_file.name).stem) or "workbook"
            destination = Path(f"uploaded_{timestamp}_{safe_stem}.xlsx")
            destination.write_bytes(uploaded_bytes)
            st.session_state.uploaded_file_signature = file_signature
            initialize_state(str(destination), uploaded_file.name)
            trigger_rerun()
            st.stop()

    excel_files = list_excel_files()
    if not excel_files:
        st.warning("No Excel workbooks found. Upload a workbook to get started.")
        return

    default_index = 0
    if "excel_path" in st.session_state and st.session_state.excel_path in excel_files:
        default_index = excel_files.index(st.session_state.excel_path)

    selected_file = st.sidebar.selectbox("Workbook", excel_files, index=default_index, key="workbook_select")

    if "excel_path" not in st.session_state or selected_file != st.session_state.excel_path:
        initialize_state(selected_file, Path(selected_file).name)

    st.sidebar.metric("Passed", st.session_state.pass_count)
    st.sidebar.metric("Bulleted", st.session_state.bullet_count)
    st.sidebar.metric("Total Reviewed", st.session_state.total_reviewed)

    if st.session_state.get("source_label"):
        st.sidebar.caption(f"Reviewing: {st.session_state.source_label}")

    if st.session_state.removed_rows:
        st.sidebar.info(f"Removed {st.session_state.removed_rows} rows without a URL")

    if st.session_state.last_save_message:
        st.sidebar.caption(st.session_state.last_save_message)

    if st.sidebar.button("Save now"):
        save_progress(force=True)
        trigger_rerun()

    if 'df' in st.session_state:
        refresh_export_name()
        if st.session_state.get('reset_export_name'):
            st.session_state.export_name = st.session_state.initial_export_name
            st.session_state.reset_export_name = False

        pending_name = st.session_state.pop('pending_export_name', None)
        if pending_name is not None:
            st.session_state.export_name = pending_name
        elif 'export_name' not in st.session_state:
            st.session_state.export_name = st.session_state.initial_export_name

        if 'export_name' in st.session_state:
            st.sidebar.text_input("Git filename", value=st.session_state.export_name, key="export_name")

            local_filename = st.session_state.export_name or "reviewed.xlsx"
            download_buffer = BytesIO()
            st.session_state.df.to_excel(download_buffer, index=False)
            download_buffer.seek(0)
            st.sidebar.download_button(
                "Save locally",
                data=download_buffer,
                file_name=local_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_local_copy",
            )

            word_buffer = BytesIO()
            st.session_state.doc.save(word_buffer)
            word_buffer.seek(0)
            st.sidebar.download_button(
                "Save Word summary",
                data=word_buffer,
                file_name=WORD_FILENAME,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_word_copy",
            )

            if st.sidebar.button("Save to Git"):
                destination = Path(st.session_state.export_name)
                if not destination.is_absolute():
                    destination = Path.cwd() / destination
                destination.parent.mkdir(parents=True, exist_ok=True)
                success, message = save_and_git_commit(destination, st.session_state.df)
                if success:
                    st.session_state.last_export_message = message
                    st.sidebar.success(message)
                    st.session_state.initial_export_name = build_export_filename(st.session_state.df)
                    st.session_state.reset_export_name = True
                else:
                    st.session_state.last_export_message = message
                    st.sidebar.error(message)
    if st.session_state.get("last_export_message"):
        st.sidebar.caption(st.session_state.last_export_message)

    if st.session_state.total_reviewed:
        st.sidebar.warning("Existing review marks detected.")
        if st.sidebar.button("Reset for re-review"):
            reset_for_rereview()
            trigger_rerun()

    advance_to_next_unreviewed()

    df = st.session_state.df
    idx = st.session_state.current_index

    if idx >= len(df):
        st.success("All rows reviewed.")
        return

    row = df.iloc[idx]
    st.subheader(f"Row {idx + 1} of {len(df)}")
    st.write(row.get("Text", ""))

    flag_value = row.get("bad_words_found", "")
    if pd.notna(flag_value) and str(flag_value).strip():
        st.warning(f"Flags: {flag_value}")

    quote_flag = row.get("is_quote_tweet") or row.get("Quote Tweet")
    if pd.notna(quote_flag) and quote_flag:
        st.info("QUOTE TWEET")

    url = row.get("URL", "")
    if isinstance(url, str) and url.strip():
        st.markdown(f"[Open Link]({url})")

    st.caption(f"Progress saves every {SAVE_INTERVAL} actions.")

    if 'topic_input' not in st.session_state:
        st.session_state.topic_input = ''
    if 'topic_select' not in st.session_state:
        st.session_state.topic_select = ''
    if 'clear_topic_inputs' not in st.session_state:
        st.session_state.clear_topic_inputs = False
    if st.session_state.clear_topic_inputs:
        st.session_state.topic_input = ''
        st.session_state.topic_select = ''
        st.session_state.clear_topic_inputs = False

    columns = st.columns(3)
    ensure_hotkeys_script()
    if columns[0].button("Pass (Q)", key="pass_button"):
        handle_pass()
        trigger_rerun()

    with st.expander("Topic options", expanded=False):
        existing_topics = [''] + sorted(st.session_state.topic_history)
        st.selectbox("Choose existing topic", existing_topics, key="topic_select")
        st.text_input("Or enter a topic", key="topic_input")

    if columns[1].button("Bullet (W)", key="bullet_button"):
        topic_choice = (st.session_state.topic_input or '').strip() or (st.session_state.topic_select or '').strip()
        if not topic_choice:
            st.warning("Provide a topic before marking as bullet.")
        else:
            handle_bullet(topic_choice)
            st.session_state.clear_topic_inputs = True
            trigger_rerun()

    if columns[2].button("Undo last"):
        if handle_back():
            trigger_rerun()
        else:
            st.info("Nothing to undo yet.")



if __name__ == "__main__":
    main()






