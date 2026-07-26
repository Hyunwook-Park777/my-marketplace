# -*- coding: utf-8 -*-
"""Assemble a research-note .docx from a template, schedule, notes and figures.

Clones the template's single note-page block (page-number paragraph + content
table + footer table) into one page per schedule entry and fills each one:

  [blank] title [blank] *content-lines [blank] figure  + trailing blanks

- Names in the footer are spaced ("박현욱" -> "박 현 욱") and centered.
- Writers listed in formatting.no_figure_writers get no figure.
- Each note is kept to exactly one page (verify afterwards with render_check.py).

Usage:
    python assemble_docx.py config.json [work_dir]

work_dir (default ".") must contain:
    schedule.json                    (from build_schedule.py)
    notes_*.json  or  notes.json     ([{page,title,lines}] per writer, or merged)
    figure_map.json                  (optional: {"<page>": "path/to/image"})
"""
import sys, os, glob, json, copy, re, math
from docx import Document
from docx.shared import Pt, Cm
from docx.table import Table
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def ptext(p):
    return "".join(t.text or "" for t in p.findall(".//" + qn("w:t")))


def add_page_break_before(p):
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr"); p.insert(0, pPr)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.insert(0, OxmlElement("w:pageBreakBefore"))


def set_para_text(p, text):
    ts = p.findall(".//" + qn("w:t"))
    if ts:
        ts[0].text = text
        for t in ts[1:]:
            t.text = ""


def load_notes(work):
    notes = {}
    files = glob.glob(os.path.join(work, "notes_*.json")) or \
        ([os.path.join(work, "notes.json")] if os.path.exists(os.path.join(work, "notes.json")) else [])
    for fn in files:
        for e in json.load(open(fn, encoding="utf-8")):
            notes[int(e["page"])] = e
    return notes


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    work = sys.argv[2] if len(sys.argv) > 2 else "."
    fmt = cfg.get("formatting", {})
    FONT = fmt.get("font", "Gulim"); SIZE = Pt(fmt.get("size_pt", 11))
    bw, bh = fmt.get("figure_max_cm", [12.0, 6.5])
    BOX_W, BOX_H = Cm(bw), Cm(bh)
    NOFIG = set(fmt.get("no_figure_writers", []))
    SPACE = fmt.get("space_names", True)
    CENTER = fmt.get("center_footer", True)
    FILL = fmt.get("fill_to_page", True)

    sched = json.load(open(os.path.join(work, "schedule.json"), encoding="utf-8"))
    sched.sort(key=lambda r: r["page"])
    notes = load_notes(work)
    figmap = {}
    fp = os.path.join(work, "figure_map.json")
    if os.path.exists(fp):
        figmap = {int(k): v for k, v in json.load(open(fp, encoding="utf-8")).items()}

    def spaced(n):
        return " ".join(list(n)) if SPACE else n

    def pic_size(path):
        try:
            from PIL import Image
            iw, ih = Image.open(path).size
            return {"height": BOX_H} if int(BOX_W * ih / iw) > BOX_H else {"width": BOX_W}
        except Exception:
            return {"width": BOX_W}

    def line(cell, text="", bold=False, center=False):
        p = cell.add_paragraph()
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if text:
            r = p.add_run(text); r.font.name = FONT; r.font.size = SIZE; r.bold = bold
        return p

    def clear(cell):
        for p in list(cell.paragraphs):
            p._element.getparent().remove(p._element)

    def fill_content(cell, title, lines, image):
        clear(cell)
        if fmt.get("blank_before_title", True):
            line(cell)
        line(cell, title, bold=True)
        if fmt.get("blank_after_title", True):
            line(cell)
        for ln in lines:
            line(cell, ln)
        if image and os.path.exists(image):
            if fmt.get("blank_before_figure", True):
                line(cell)
            p = line(cell, center=True); p.add_run().add_picture(image, **pic_size(image))
            trailing = 1
        elif FILL:
            disp = sum(max(1, math.ceil(len(l) / 36)) for l in lines)
            trailing = max(1, min(12, 34 - 3 - disp))   # fill toward bottom, capped to avoid overflow
        else:
            trailing = 1
        for _ in range(trailing):
            line(cell)

    def fill_footer(tbl, writer, rec, confirmer, conf):
        def sc(cell, text):
            cell.text = text
            for p in cell.paragraphs:
                if CENTER:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.name = FONT; r.font.size = SIZE
        sc(tbl.cell(0, 1), f"{spaced(writer)}   (인)")
        sc(tbl.cell(0, 3), rec)
        sc(tbl.cell(1, 1), f"{spaced(confirmer)}   (인)")
        sc(tbl.cell(1, 3), conf)
        if CENTER:
            for r in range(2):
                for c in (0, 2):
                    for p in tbl.cell(r, c).paragraphs:
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    d = Document(cfg["template_docx"])
    body = d.element.body
    children = list(body)
    start = next((i for i, ch in enumerate(children)
                  if ch.tag.endswith("}p") and re.search(r"\d{3}\(", ptext(ch))), None)
    if start is None:
        sys.exit("Could not locate the template's page-number block. See references/template-anatomy.md")
    # detect block size: pagenum P .. up to and including the next footer table
    BLOCK = cfg.get("template", {}).get("block_len", 4)
    # count original note pages by scanning consecutive blocks that start with a page-number P
    n_orig = 0
    i = start
    while i < len(children) and children[i].tag.endswith("}p") and re.search(r"\d{3}\(", ptext(children[i])):
        n_orig += 1; i += BLOCK
    end = start + BLOCK * n_orig
    template_block = [copy.deepcopy(e) for e in children[start:start + BLOCK]]
    anchor = children[end]
    for e in children[start:end]:
        body.remove(e)

    for entry in sched:
        pg = entry["page"]
        blk = [copy.deepcopy(e) for e in template_block]
        pnum_p, content_tbl, sep_p, footer_tbl = blk
        add_page_break_before(pnum_p)
        set_para_text(pnum_p, f"{pg:03d}(페이지)")
        for e in blk:
            anchor.addprevious(e)
        fill_footer(Table(footer_tbl, d), entry["writer"], entry["rec"], entry["confirmer"], entry["conf"])
        note = notes.get(pg)
        if note:
            image = None if entry["writer"] in NOFIG else figmap.get(pg)
            fill_content(Table(content_tbl, d).cell(0, 0), note["title"], note["lines"], image)

    d.save(cfg["output_docx"])
    filled = sum(1 for e in sched if e["page"] in notes)
    print(f"saved {cfg['output_docx']} | pages={len(sched)} filled={filled} "
          f"figs={sum(1 for e in sched if e['writer'] not in NOFIG and figmap.get(e['page']))}")


if __name__ == "__main__":
    main()
