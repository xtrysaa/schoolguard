"""Собирает научную работу в docs/SchoolGuard_paper.docx из tools/paper_content.py.

    python tools/make_figures.py --scores reports/v2_test_scores.json
    python tools/build_paper.py
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from paper_content import BLOCKS, TITLE  # noqa: E402

OUT = ROOT / "docs" / "SchoolGuard_paper.docx"
BODY_FONT, BODY_SIZE = "Arial", 11
# титульный лист: заглушки; настоящие данные вписываются в готовом документе
TITLE_LINES = [("Учебное заведение, город", 30), ("Фамилия Имя автора", 30), ("Класс", 30),
               (f'"{TITLE}"', 35), ("Направление, секция", 30), ("Руководитель", 30), ("Город. Год", 30)]


def set_font(run, name=BODY_FONT, size=None, bold=None, italic=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts"); rpr.insert(0, rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), name)
    if size: run.font.size = Pt(size)
    if bold is not None: run.font.bold = bold
    if italic is not None: run.font.italic = italic
    if color is not None: run.font.color.rgb = color


def add_rich(par, text, size=None, italic=None):
    """Текст с **жирными** фрагментами."""
    for i, part in enumerate(re.split(r"\*\*", text)):
        if part:
            set_font(par.add_run(part), size=size, bold=(i % 2 == 1) or None, italic=italic)


LINK_RE = re.compile(r"https?://[^\s)]+?(?=[.,;)]?(?:\s|$))|(?<=DOI: )10\.\S+?(?=\.?(?:\s|$))")


def add_link(par, text, url):
    """Кликабельная ссылка (синяя, подчёркнутая)."""
    rid = par.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid)
    r = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
    col = OxmlElement("w:color"); col.set(qn("w:val"), "1155CC"); rpr.append(col)
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rpr.append(u)
    r.append(rpr)
    t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = text; r.append(t)
    h.append(r); par._p.append(h)


def add_with_links(par, text):
    """Пункт списка литературы: адреса и DOI становятся ссылками."""
    pos = 0
    for m in LINK_RE.finditer(text):
        if m.start() > pos:
            set_font(par.add_run(text[pos:m.start()]))
        s = m.group(0)
        add_link(par, s, s if s.startswith("http") else "https://doi.org/" + s)
        pos = m.end()
    if pos < len(text):
        set_font(par.add_run(text[pos:]))


def style_setup(doc):
    st = doc.styles
    n = st["Normal"]
    n.font.name = BODY_FONT; n.font.size = Pt(BODY_SIZE)
    n.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    n.paragraph_format.line_spacing = 1.0
    n.paragraph_format.space_after = Pt(6)
    for name, size in (("Heading 1", 20), ("Heading 2", 15), ("Heading 3", 13)):
        h = st[name]
        h.font.name = BODY_FONT; h.font.size = Pt(size); h.font.bold = True; h.font.color.rgb = RGBColor(0, 0, 0)
        rpr = h.element.get_or_add_rPr()
        rf = rpr.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts"); rpr.insert(0, rf)
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rf.set(qn(a), BODY_FONT)
        for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            if rf.get(qn(a)) is not None:
                del rf.attrib[qn(a)]
        h.paragraph_format.keep_with_next = True
        h.paragraph_format.space_before = Pt(18 if name == "Heading 1" else 12)
        h.paragraph_format.space_after = Pt(8)


def new_num(doc, style_name: str) -> int:
    """Новый экземпляр нумерации на основе стиля списка, начинающийся с 1."""
    numbering = doc.part.numbering_part.numbering_definitions._numbering
    style = doc.styles[style_name]
    num_id_el = style.element.pPr.find(qn("w:numPr")).find(qn("w:numId"))
    base = numbering.num_having_numId(int(num_id_el.get(qn("w:val"))))
    abstract_id = base.abstractNumId.val
    num = numbering.add_num(abstract_id)
    ov = OxmlElement("w:lvlOverride"); ov.set(qn("w:ilvl"), "0")
    so = OxmlElement("w:startOverride"); so.set(qn("w:val"), "1")
    ov.append(so); num.append(ov)
    return num.numId


def set_num(par, num_id: int):
    ppr = par._p.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    il = OxmlElement("w:ilvl"); il.set(qn("w:val"), "0")
    ni = OxmlElement("w:numId"); ni.set(qn("w:val"), str(num_id))
    numpr.append(il); numpr.append(ni); ppr.append(numpr)


def shade(cell, hex_fill):
    tcpr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), hex_fill)
    tcpr.append(sh)


def no_split_rows(table):
    for row in table.rows:
        trpr = row._tr.get_or_add_trPr()
        cs = OxmlElement("w:cantSplit"); trpr.append(cs)
    hdr = table.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader"); hdr.append(th)


def field(par, instr, cached_runs=None):
    def fc(t):
        r = OxmlElement("w:r"); f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), t); r.append(f); return r
    par._p.append(fc("begin"))
    r = OxmlElement("w:r"); it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instr} "; r.append(it)
    par._p.append(r)
    par._p.append(fc("separate"))
    for t in cached_runs or ["1"]:
        rr = OxmlElement("w:r"); tt = OxmlElement("w:t"); tt.set(qn("xml:space"), "preserve"); tt.text = t; rr.append(tt); par._p.append(rr)
    par._p.append(fc("end"))


def hr(par):
    ppr = par._p.get_or_add_pPr()
    b = OxmlElement("w:pBdr"); bt = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "999999")):
        bt.set(qn(k), v)
    b.append(bt); ppr.append(b)


def build():
    doc = Document()
    style_setup(doc)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Inches(1))
    sec.different_first_page_header_footer = True
    fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field(fp, "PAGE")

    # титульный лист, как в образце
    for i, (text, size) in enumerate(TITLE_LINES):
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.0
        set_font(p.add_run(text), "Times New Roman", size)
    doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)

    # оглавление: поле TOC с заранее заполненным списком разделов
    h = doc.add_paragraph(style="Heading 1"); set_font(h.add_run("Оглавление"), size=20, bold=True)
    heads = [(b[0], b[1]) for b in BLOCKS if b[0] in ("h1", "h2") and b[1] != "Исследовательская часть"]
    toc = doc.add_paragraph()
    field(toc, 'TOC \\o "1-2" \\h \\z \\u', [""])
    # список-заглушка внутри результата поля: каждая строка отдельным абзацем нельзя, поэтому кладём перевод строки
    rlist = toc._p.findall(qn("w:r"))
    sep_idx = [i for i, r in enumerate(rlist) if r.find(qn("w:fldChar")) is not None and r.find(qn("w:fldChar")).get(qn("w:fldCharType")) == "separate"][0]
    anchor = rlist[sep_idx]
    for lvl, text in reversed(heads):
        r = OxmlElement("w:r")
        if lvl == "h1":
            rpr = OxmlElement("w:rPr"); bb = OxmlElement("w:b"); rpr.append(bb); r.append(rpr)
        t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve"); t.text = ("" if lvl == "h1" else "    ") + text; r.append(t)
        br = OxmlElement("w:br"); r.append(br)
        anchor.addnext(r)
    toc.add_run().add_break(WD_BREAK.PAGE)

    ref_num = None
    for b in BLOCKS:
        kind = b[0]
        if kind in ("h1", "h2"):
            p = doc.add_paragraph(style="Heading 1" if kind == "h1" else "Heading 2")
            set_font(p.add_run(b[1]), bold=True)
        elif kind == "p":
            p = doc.add_paragraph(); add_rich(p, b[1])
        elif kind == "ul":
            for item in b[1]:
                p = doc.add_paragraph(style="List Bullet"); add_rich(p, item)
                p.paragraph_format.space_after = Pt(3)
        elif kind in ("ol", "ol_ref"):
            if kind == "ol" or ref_num is None:
                nid = new_num(doc, "List Number")
                if kind == "ol_ref":
                    ref_num = nid
            nid = ref_num if kind == "ol_ref" else nid
            for item in b[1]:
                p = doc.add_paragraph(style="List Number"); set_num(p, nid)
                if kind == "ol_ref":
                    add_with_links(p, item)
                else:
                    add_rich(p, item)
                p.paragraph_format.space_after = Pt(3)
        elif kind == "formula":
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(8)
            set_font(p.add_run(b[1]), "Cambria", 12, italic=True)
        elif kind == "table":
            cap = doc.add_paragraph(); cap.paragraph_format.keep_with_next = True
            cap.paragraph_format.space_before = Pt(8)
            set_font(cap.add_run(b[1]), bold=True, size=10.5)
            rows = b[2]
            t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    c = t.cell(i, j); c.text = ""
                    cp = c.paragraphs[0]; cp.paragraph_format.space_after = Pt(0); cp.paragraph_format.line_spacing = 1.0
                    set_font(cp.add_run(val), size=9.5, bold=(i == 0) or (row[0] in ("Итого",) and j == 0) or None)
                    if i == 0:
                        shade(c, "E8EEF1")
            no_split_rows(t)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)
        elif kind == "fig":
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.keep_with_next = True
            p.paragraph_format.space_before = Pt(6)
            p.add_run().add_picture(str(ROOT / b[1]), width=Inches(b[3]))
            cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_font(cap.add_run(b[2]), size=9.5, italic=True)
        elif kind == "rule":
            hr(doc.add_paragraph())
        elif kind == "break":
            doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)
    OUT.parent.mkdir(exist_ok=True)
    doc.save(OUT)
    print(OUT, OUT.stat().st_size // 1024, "КБ")


if __name__ == "__main__":
    build()
