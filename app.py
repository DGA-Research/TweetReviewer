import os
import re
import io
import pandas as pd
from datetime import datetime
from docx import Document
from docx.shared import Pt
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import streamlit as st
from streamlit_free_text_select import st_free_text_select

st.set_page_config(page_title="Tweet Reviewer", layout="wide")

SAVE_INTERVAL = 20

# --- Upload ---
st.title("📑 Tweet Reviewer")

platform = st.text_input("Enter Social Media Platform: ")
handle = st.text_input("Enter Social Media Handle: (ex: JoshSchoemann) ")
uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

# Add a reset button next to it
if st.button("🔄 Reset Session"):
    for key in st.session_state.keys():
        del st.session_state[key]
        
topics = ['Key Moments', 'Campaigns For Congress', 'Cycle Year', 'Abortion and Family Planning Issues', 'Agriculture Issues', 'Budget Issues', 'Campaign Finance and Election Law Issues', 'Consumer Issues', 'Crime and Public Safety Issues', 'Defense Issues', 'Economy and Job Issues', 'Education Issues', 'Energy Issues', 'Envionrmental Issues', 'Fema and Disaster Relief Issues', 'Foreign Policy Issues', 'Gun Issues', 'Health Care Issues', 'Housing Issues', 'Immigration and Border Issues', 'Labor and Working Family Issues', 'LGBT Issues', 'Military Personnel Issues', 'Seniors Issues','Tax Issues', 'Technology Issues', 'Terrorism and Homeland Security', 'Trade Issues', 'Transportation Issues', 'Veteran\'s Issues', 'Women\'s Issues']

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df.columns = df.columns.str.strip()
    df = df[df["Text"].notna()].reset_index(drop=True)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    if "df" not in st.session_state:
        df = pd.read_excel(uploaded_file)
        if "Reviewed Passed" not in df.columns:
            df["Reviewed Passed"] = False
        if "Reviewed Bulleted" not in df.columns:
            df["Reviewed Bulleted"] = False
        st.session_state.df = df

        # Word doc
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(10)
        if "Heading 2" not in doc.styles:
            style = doc.styles.add_style("Heading 2", WD_STYLE_TYPE.PARAGRAPH)
            style.font.name = "Arial"
            style.font.size = Pt(12)
            style.font.bold = True
        st.session_state.doc = doc

        st.session_state.current_index = 0
        st.session_state.pass_count = df["Reviewed Passed"].sum()
        st.session_state.bullet_count = df["Reviewed Bulleted"].sum()
        st.session_state.review_count = int(st.session_state.pass_count + st.session_state.bullet_count)
        st.session_state.used_topics = set()
        st.session_state.topic_history = []
        st.session_state.history_stack = []

    df = st.session_state.df

    def normalize_spaces(text):
        text = re.sub(r'([.?!]) {2,}', r'\1 ', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    def parse_date(date_value):
        known_formats = [
            "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
            "%m/%d/%y", "%d/%m/%y", "%B %d, %Y",
            "%b %d, %Y", "%d %B %Y", "%d %b %Y"
        ]
        for fmt in known_formats:
            try:
                return datetime.strptime(str(date_value), fmt)
            except (ValueError, TypeError):
                continue
        return None

    def format_text_for_bullet(row, topic):
        topic_upper = topic.upper()
        doc = st.session_state.doc

        if topic_upper not in st.session_state.used_topics:
            doc.add_paragraph(topic_upper, style="Heading 2")
            st.session_state.used_topics.add(topic_upper)
        
        # st.markdown(row)
        text = row["Text"]
        url = row["URL"]
        date = parse_date(row["Date"])
        date_str = f"{date.month}/{date.day}/{str(date.year)[2:]}" if date else "??/??/??"
        text = text.replace('"', "'").replace("\n", "\u00A0")
        text = normalize_spaces(text)
        quoted = f'"{text}"'

        para1 = doc.add_paragraph()
        run1 = para1.add_run(quoted + " ")
        run1.font.name = "Arial"
        run1.font.size = Pt(10)

        add_hyperlink_date_only(para1, f"[{platform}, @{handle}, ", date_str, "]", url)
        doc.add_paragraph()

        para2 = doc.add_paragraph()
        para2.alignment = 1
        add_hyperlink_date_only(para2, f"[{platform}, @{handle}, ", date_str, "]", url)
        doc.add_paragraph()

    def add_hyperlink_date_only(paragraph, prefix, date_part, suffix, url):
        run1 = paragraph.add_run(prefix)
        run1.font.name = "Arial"
        run1.font.size = Pt(10)

        part = paragraph.part
        r_id = part.relate_to(url, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True)

        hyperlink = OxmlElement('w:hyperlink')
        hyperlink.set(qn('r:id'), r_id)

        new_run = OxmlElement('w:r')
        rPr = OxmlElement('w:rPr')
        rStyle = OxmlElement('w:rStyle')
        rStyle.set(qn('w:val'), 'Hyperlink')
        rPr.append(rStyle)
        color = OxmlElement('w:color')
        color.set(qn('w:val'), '0000FF')
        rPr.append(color)
        underline = OxmlElement('w:u')
        underline.set(qn('w:val'), 'single')
        rPr.append(underline)
        new_run.append(rPr)

        t = OxmlElement('w:t')
        t.text = date_part
        new_run.append(t)

        hyperlink.append(new_run)
        paragraph._p.append(hyperlink)

        run3 = paragraph.add_run(suffix)
        run3.font.name = "Arial"
        run3.font.size = Pt(10)

    def save_if_needed():
        if st.session_state.review_count % SAVE_INTERVAL == 0:
            st.success("Progress auto-saved!")

    def handle_pass():
        idx = st.session_state.current_index
        df.at[idx, "Reviewed Passed"] = True
        st.session_state.history_stack.append((idx, "pass"))
        st.session_state.pass_count += 1
        st.session_state.review_count += 1
        save_if_needed()
        st.session_state.current_index += 1

    def handle_bullet(topic):
        idx = st.session_state.current_index
        df.at[idx, "Reviewed Bulleted"] = True
        st.session_state.history_stack.append((idx, "bullet"))
        format_text_for_bullet(df.iloc[idx], topic)
        st.session_state.bullet_count += 1
        st.session_state.review_count += 1
        save_if_needed()
        st.session_state.current_index += 1

    def handle_back():
        if st.session_state.history_stack:
            last_index, action = st.session_state.history_stack.pop()
            if action == "pass":
                df.at[last_index, "Reviewed Passed"] = False
                st.session_state.pass_count -= 1
            elif action == "bullet":
                df.at[last_index, "Reviewed Bulleted"] = False
                st.session_state.bullet_count -= 1
            st.session_state.review_count -= 1
            st.session_state.current_index = last_index

    # --- Skip reviewed rows ---
    while st.session_state.current_index < len(df) and (
        df.at[st.session_state.current_index, "Reviewed Passed"]
        or df.at[st.session_state.current_index, "Reviewed Bulleted"]
    ):
        st.session_state.current_index += 1

    if st.session_state.current_index >= len(df):
        st.success("✅ All rows reviewed!")
    else:
        row = df.iloc[st.session_state.current_index]
        st.markdown(f"### {row['Text']}")
        st.markdown(f"[Open Link]({row['URL']})")
        
        st.write(f"**Passed:** {int(st.session_state.pass_count)} | **Bulleted:** {int(st.session_state.bullet_count)} | **Total:** {int(st.session_state.review_count)}")

        col1, col2, col3 = st.columns(3)

        if col1.button("✅ Pass"):
            handle_pass()

        with col2:
            # topic = col2.text_input("Topic", key="topic_input") 
            topic = st_free_text_select(
                label="Topic",
                options=topics,
                index=None,
                format_func=lambda x: x.lower(),
                placeholder="Enter Topic",
                disabled=False,
                delay=300,
                label_visibility="visible",
            )
            if topic not in topics:
                topics.append(topic)

        if col2.button("💬 Bullet"):
            if topic.strip():
                handle_bullet(topic.strip())

        if col1.button("⬅️ Back"):
            handle_back()

    # --- Downloads ---
    st.divider()

    # Save DataFrame to BytesIO
    excel_io = io.BytesIO()
    df.to_excel(excel_io, index=False, engine="openpyxl")
    excel_io.seek(0)

    st.download_button(
        label="📥 Download Updated Excel",
        data=excel_io,
        file_name="updated_review.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Save Word doc to BytesIO
    word_io = io.BytesIO()
    st.session_state.doc.save(word_io)
    word_io.seek(0)

    st.download_button(
        label="📄 Download Word Document",
        data=word_io,
        file_name="bullets.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
else:
    st.info("⬆️ Please upload an Excel file to begin.")

