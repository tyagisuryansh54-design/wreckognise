"""Render PROJECT_REPORT.md to a formatted PDF.

A small purpose-built markdown renderer rather than a general one: this document
uses a known subset (headings, tables, fenced code, bold, inline code, lists,
rules, links) and rendering exactly that subset well beats a generic converter
that mishandles the tables.

ReportLab's built-in fonts lack many of the Unicode characters used in the
source -- box drawing, sigma, superscripts, arrows -- which render as solid
black boxes rather than failing loudly. Everything risky is mapped to a safe
equivalent before it reaches the canvas.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0A192F")
AZURE = colors.HexColor("#0077B6")
TEAL = colors.HexColor("#1E3A3A")
SAND = colors.HexColor("#EFECE6")
GREY = colors.HexColor("#5A6672")

# Characters the standard 14 fonts cannot draw. Left unmapped they appear as
# filled rectangles, which looks like a rendering bug in a submitted document.
SAFE = {
    "—": "-", "–": "-", "→": "->", "▶": ">", "▼": "v", "←": "<-",
    "·": "-", "±": "+/-", "×": "x", "σ": "sigma", "²": "^2", "√": "sqrt",
    "−": "-", "≥": ">=", "≤": "<=", "≈": "~", "✓": "[ok]", "•": "-",
    "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
    "┬": "+", "┴": "+", "┼": "+", "─": "-", "│": "|", "╸": "-",
}


def sanitise(text: str) -> str:
    for bad, good in SAFE.items():
        text = text.replace(bad, good)
    return text


def inline(text: str) -> str:
    """Markdown inline formatting -> ReportLab markup, escaping XML first."""
    text = sanitise(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#0077B6">\1</link>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+?)`", r'<font face="Courier" size="8.5" color="#1E3A3A">\1</font>', text)
    return text


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=24, leading=28, textColor=NAVY, spaceAfter=4),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontName="Helvetica",
                                   fontSize=11, leading=15, textColor=GREY, spaceAfter=14),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=16, leading=20, textColor=NAVY,
                             spaceBefore=16, spaceAfter=7),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12.5, leading=16, textColor=TEAL,
                             spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold",
                             fontSize=10.5, leading=14, textColor=TEAL,
                             spaceBefore=9, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["Normal"], fontName="Helvetica",
                               fontSize=9.5, leading=13.5, textColor=colors.HexColor("#1a1a1a"),
                               alignment=TA_LEFT, spaceAfter=6),
        "bullet": ParagraphStyle("bu", parent=base["Normal"], fontName="Helvetica",
                                 fontSize=9.5, leading=13.5, leftIndent=12,
                                 bulletIndent=3, spaceAfter=3),
        "code": ParagraphStyle("c", parent=base["Code"], fontName="Courier",
                               fontSize=8, leading=10.5, textColor=colors.HexColor("#0A192F"),
                               backColor=SAND, borderPadding=6,
                               leftIndent=4, rightIndent=4, spaceBefore=4, spaceAfter=8),
        "th": ParagraphStyle("th", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=9.5, leading=13.5, textColor=colors.white),
        "quote": ParagraphStyle("q", parent=base["Normal"], fontName="Helvetica-Oblique",
                                fontSize=9.5, leading=13.5, leftIndent=14,
                                textColor=TEAL, spaceAfter=6),
    }


def make_table(rows: list[list[str]], styles, width: float):
    header, *body = rows
    ncols = len(header)
    # A key/value table is written with an empty header row; a navy bar with
    # nothing in it just looks like a rendering fault, so drop it.
    has_header = any(c.strip() for c in header)
    if not has_header:
        body = rows[1:]
    data = [[Paragraph(inline(c), styles["th"]) for c in header]] if has_header else []
    for row in body:
        row = (row + [""] * ncols)[:ncols]
        data.append([Paragraph(inline(c), styles["body"]) for c in row])

    # Size columns by the text they actually hold, damped so one long cell does
    # not starve the rest, and floored so a narrow "#" column stays readable.
    body_rows = rows[1:] if has_header else rows
    weights = []
    for c in range(ncols):
        longest = max((len(r[c]) for r in rows if c < len(r)), default=1)
        typical = max((len(r[c]) for r in body_rows if c < len(r)), default=1)
        weights.append(max(longest, typical * 1.5) ** 0.6)
    total = sum(weights)
    floor = 0.08
    widths = [max(w / total, floor) for w in weights]
    scale = 1.0 / sum(widths)
    widths = [width * w * scale for w in widths]

    table = Table(data, colWidths=widths, repeatRows=1 if has_header else 0, hAlign="LEFT")
    first_body = 1 if has_header else 0
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY if has_header else colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9CFD6")),
        ("ROWBACKGROUNDS", (0, first_body), (-1, -1),
         [colors.white, colors.HexColor("#F7F5F1")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def convert(src: Path, dst: Path) -> int:
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(dst), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Wreckognise - Project Report",
        author="Suryansh Tyagi",
        subject="Smart India Hackathon 2026",
    )
    avail = doc.width
    story: list = []
    lines = src.read_text(encoding="utf-8").splitlines()

    i = 0
    in_code = False
    code_buf: list[str] = []
    table_buf: list[list[str]] = []

    def flush_table():
        if table_buf:
            story.append(Spacer(1, 3))
            story.append(make_table(table_buf, styles, avail))
            story.append(Spacer(1, 8))
            table_buf.clear()

    while i < len(lines):
        line = lines[i]

        # fenced code
        if line.strip().startswith("```"):
            if in_code:
                text = "<br/>".join(
                    sanitise(l).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace(" ", "&nbsp;")
                    for l in code_buf
                ) or "&nbsp;"
                story.append(Paragraph(text, styles["code"]))
                code_buf.clear()
            in_code = not in_code
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # tables
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):   # separator row
                i += 1
                continue
            table_buf.append(cells)
            i += 1
            continue
        flush_table()

        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#C9CFD6")))
            story.append(Spacer(1, 6))
            i += 1
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            if level == 1 and not story:
                story.append(Paragraph(inline(text), styles["title"]))
            elif level == 1:
                story.append(PageBreak())
                story.append(Paragraph(inline(text), styles["h1"]))
            else:
                key = "h1" if level == 2 else ("h2" if level == 3 else "h3")
                story.append(Paragraph(inline(text), styles[key]))
            i += 1
            continue

        if stripped.startswith(">"):
            story.append(Paragraph(inline(stripped.lstrip("> ")), styles["quote"]))
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if m:
            story.append(Paragraph(inline(m.group(2)), styles["bullet"], bulletText=f"{m.group(1)}."))
            i += 1
            continue

        if stripped.startswith(("- ", "* ")):
            story.append(Paragraph(inline(stripped[2:]), styles["bullet"], bulletText="\u2022"))
            i += 1
            continue

        story.append(Paragraph(inline(stripped), styles["body"]))
        i += 1

    flush_table()

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(18 * mm, 10 * mm, "Wreckognise - Automated Marine Survey Agent")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc_.page}")
        canvas.setStrokeColor(colors.HexColor("#D8DCE1"))
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"  wrote {dst}  ({dst.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    name = sys.argv[1] if len(sys.argv) > 1 else "PROJECT_REPORT"
    raise SystemExit(convert(root / f"{name}.md", root / f"{name}.pdf"))
