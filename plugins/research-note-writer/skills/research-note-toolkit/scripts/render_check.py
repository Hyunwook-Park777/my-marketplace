# -*- coding: utf-8 -*-
"""Render a .docx to PDF via Word COM and report total pages + per-note overflow.

The one-page-per-note rule cannot be checked from the .docx alone (Word paginates
at render time), so this exports a PDF and inspects it. If a schedule.json is given
and PyMuPDF is installed, it also lists exactly which note pages overflowed
(a page-number marker whose footer "확 인 자" spilled onto the next page).

Usage:
    python render_check.py "output.docx" [schedule.json]
"""
import sys, os


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    docx = os.path.abspath(sys.argv[1])
    pdf = os.path.splitext(docx)[0] + ".pdf"
    try:
        import win32com.client
    except ImportError:
        sys.exit("Install pywin32:  pip install pywin32  (Windows + Microsoft Word required)")
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(docx, ReadOnly=True)
        doc.Repaginate()
        pages = doc.ComputeStatistics(2)          # wdStatisticPages
        doc.ExportAsFixedFormat(pdf, 17)          # wdExportFormatPDF
        doc.Close(False)
    finally:
        word.Quit()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"total_pages={pages}  ->  {pdf}")

    if len(sys.argv) > 2:
        try:
            import pymupdf, re
        except ImportError:
            print("(install pymupdf to get the per-note overflow list)"); return
        d = pymupdf.open(pdf)
        overflow = []
        for i in range(d.page_count):
            txt = d[i].get_text()
            has_footer = "확 인 자" in txt or "확인자" in txt.replace(" ", "")
            for num in re.findall(r"(\d{3})\(", txt):
                if not has_footer:
                    overflow.append(int(num))
        print(f"overflow_notes={sorted(set(overflow)) or 'NONE'}")


if __name__ == "__main__":
    main()
