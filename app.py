import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
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

    for column in ("Reviewed Passed", "Reviewed Bulleted"):
        if column not in df.columns:
            df[column] = False
        df[column] = df[column].fillna(False).astype(bool)

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
    st.session_state.history_stack: list[tuple[int, str, str | None]] = []
    st.session_state.current_index = 0
    st.session_state.actions_since_save = 0
    st.session_state.last_save_message = None
    st.session_state.last_export_message = None
    export_default = f"reviewed_{Path(file_path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    st.session_state.export_name = export_default
    update_counts()
    advance_to_next_unreviewed()


def update_counts() -> None:
    df = st.session_state.df
    st.session_state.pass_count = int(df["Reviewed Passed"].sum())
    st.session_state.bullet_count = int(df["Reviewed Bulleted"].sum())
    st.session_state.total_reviewed = st.session_state.pass_count + st.session_state.bullet_count


def advance_to_next_unreviewed() -> None:
    df = st.session_state.df
    idx = st.session_state.current_index
    while idx < len(df) and (df.at[idx, "Reviewed Passed"] or df.at[idx, "Reviewed Bulleted"]):
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
    idx = st.session_state.current_index
    st.session_state.df.at[idx, "Reviewed Passed"] = True
    st.session_state.history_stack.append((idx, "pass", None))
    st.session_state.current_index += 1
    update_counts()
    increment_action_counter()
    advance_to_next_unreviewed()


def handle_bullet(topic: str) -> None:
    idx = st.session_state.current_index
    topic_upper = topic.upper()
    st.session_state.df.at[idx, "Reviewed Bulleted"] = True
    st.session_state.history_stack.append((idx, "bullet", topic_upper))
    format_text_for_bullet(st.session_state.df.iloc[idx], topic_upper)
    if topic_upper not in st.session_state.topic_history:
        st.session_state.topic_history.append(topic_upper)
    st.session_state.current_index += 1
    update_counts()
    increment_action_counter()
    advance_to_next_unreviewed()


def handle_back() -> bool:
    if not st.session_state.history_stack:
        return False
    idx, action, topic = st.session_state.history_stack.pop()
    if action == "pass":
        st.session_state.df.at[idx, "Reviewed Passed"] = False
    else:
        st.session_state.df.at[idx, "Reviewed Bulleted"] = False
        if topic:
            entries = st.session_state.content_by_topic.get(topic, [])
            if entries:
                entries.pop()
                if not entries:
                    st.session_state.content_by_topic.pop(topic, None)
            rebuild_document()
    st.session_state.current_index = idx
    st.session_state.actions_since_save = max(st.session_state.actions_since_save - 1, 0)
    update_counts()
    advance_to_next_unreviewed()
    return True


def reset_for_rereview() -> None:
    st.session_state.df["Reviewed Passed"] = False
    st.session_state.df["Reviewed Bulleted"] = False
    st.session_state.history_stack = []
    st.session_state.content_by_topic = {}
    st.session_state.topic_history = []
    st.session_state.current_index = 0
    st.session_state.actions_since_save = 0
    st.session_state.clear_topic_inputs = False
    st.session_state.doc = prepare_document(Document())
    update_counts()
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

    if 'export_name' in st.session_state:
        st.sidebar.text_input("Export reviewed copy as", key="export_name")
        if st.sidebar.button("Export reviewed copy"):
            destination = Path(st.session_state.export_name)
            if not destination.suffix:
                destination = destination.with_suffix(".xlsx")
            try:
                st.session_state.df.to_excel(destination, index=False)
                st.session_state.last_export_message = f"Saved reviewed copy to {destination.resolve()}"
                st.sidebar.success(st.session_state.last_export_message)
            except Exception as exc:
                st.sidebar.error(f"Failed to export: {exc}")
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
    if columns[0].button("Pass"):
        handle_pass()
        trigger_rerun()

    with st.expander("Topic options", expanded=False):
        existing_topics = [''] + sorted(st.session_state.topic_history)
        st.selectbox("Choose existing topic", existing_topics, key="topic_select")
        st.text_input("Or enter a topic", key="topic_input")

    if columns[1].button("Bullet"):
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




