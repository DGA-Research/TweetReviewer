import pandas as pd
from datetime import datetime
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# ---------- USER SETTINGS ----------
INPUT_XLSX   = "Tweets to put in bullet format.xlsx"   # your Excel file
SHEET_NAME   = 0                                       # or a sheet name string
OUTPUT_DOCX  = "Issue Clipbook.docx"                   # output Word doc
HANDLE       = "@RandyFeenstra"                        # your constant handle
TEXT_COL     = "Text"
DATE_COL     = "Date"
URL_COL      = "URL"
FLAG_COL     = "Reviewed Bulleted"                     # Boolean column
# -----------------------------------

def to_mmddyy(d):
    """Format to M/D/YY from Excel or string date."""
    if pd.isna(d):
        return ""
    if isinstance(d, datetime):
        return f"{d.month}/{d.day}/{str(d.year)[2:]}"
    # try common string formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(str(d), fmt)
            return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"
        except ValueError:
            continue
    # fallback: just return original
    return str(d)

def ensure_url_scheme(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    if not u:
        return ""
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "https://" + u
    return u

def add_hyperlink(paragraph, text, url):
    """
    Add a blue, underlined hyperlink run (displaying `text`) pointing to `url`.
    Falls back to plain text if url is empty.
    """
    url = ensure_url_scheme(url)
    if not url:
        # fallback: plain text (no link)
        r = paragraph.add_run(text)
        r.font.name = "Arial"
        r.font.size = Pt(10)
        return

    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    # Create the run
    new_run = OxmlElement("w:r")

    # Run properties
    rPr = OxmlElement("w:rPr")

    # Set font color to blue
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0000FF")  # hex RGB
    rPr.append(color)

    # Set underline
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rPr.append(underline)

    new_run.append(rPr)

    # Add the text
    w_t = OxmlElement("w:t")
    w_t.text = text
    new_run.append(w_t)

    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def main():
    # Read and filter data
    df = pd.read_excel(INPUT_XLSX, sheet_name=SHEET_NAME)
    if FLAG_COL not in df.columns:
        raise ValueError(f"Missing column: {FLAG_COL}")
    required = [TEXT_COL, DATE_COL, URL_COL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    filtered = df[df[FLAG_COL] == True].copy()

    # Create document
    doc = Document()

    # Base font (Normal style)
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)

    for _, row in filtered.iterrows():
        text = str(row[TEXT_COL]).replace('"', "'").replace("\n", " ").strip()
        date_str = to_mmddyy(row[DATE_COL])
        url = str(row[URL_COL])

        # Line 1: "Quoted text" [X, {Handle}, {Date (hyperlinked)}]
        p1 = doc.add_paragraph()
        run1 = p1.add_run(f"\"{text}\" ")
        run1.font.name = "Arial"
        run1.font.size = Pt(10)

        pre = p1.add_run("[X, " + HANDLE + ", ")
        pre.font.name = "Arial"
        pre.font.size = Pt(10)

        add_hyperlink(p1, date_str, url)   # <-- Date is the hyperlink

        post = p1.add_run("]")
        post.font.name = "Arial"
        post.font.size = Pt(10)

        # Blank line for spacing
        doc.add_paragraph("")

        # Line 2: centered [X, {Handle}, {Date (hyperlinked)}]
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER

        pre2 = p2.add_run("[X, " + HANDLE + ", ")
        pre2.font.name = "Arial"
        pre2.font.size = Pt(10)

        add_hyperlink(p2, date_str, url)   # <-- Date is the hyperlink

        post2 = p2.add_run("]")
        post2.font.name = "Arial"
        post2.font.size = Pt(10)

        # Final blank line for spacing
        doc.add_paragraph("")

    doc.save(OUTPUT_DOCX)
    print(f"Saved {len(filtered)} bullets to {OUTPUT_DOCX}")

if __name__ == "__main__":
    main()
