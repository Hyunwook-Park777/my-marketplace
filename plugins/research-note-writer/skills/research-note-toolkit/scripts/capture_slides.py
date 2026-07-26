# -*- coding: utf-8 -*-
"""Export every slide of a .pptx to slides/slide_XXX.png via PowerPoint COM (Windows).

Use this when a source presentation should be inserted into notes verbatim
("capture the deck") rather than re-summarised. Requires Microsoft PowerPoint.

Usage:
    python capture_slides.py "deck.pptx" [out_dir=slides] [width=1280] [height=960]
"""
import sys, os


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    pptx = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(os.getcwd(), "slides")
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 960
    os.makedirs(out, exist_ok=True)
    try:
        import win32com.client
    except ImportError:
        sys.exit("Install pywin32:  pip install pywin32  (Windows + PowerPoint required)")
    ppt = win32com.client.Dispatch("PowerPoint.Application")
    try:
        pres = ppt.Presentations.Open(pptx, WithWindow=False, ReadOnly=True)
        n = pres.Slides.Count
        for i in range(1, n + 1):
            pres.Slides(i).Export(os.path.join(out, f"slide_{i:03d}.png"), "PNG", w, h)
        pres.Close()
        print(f"exported {n} slides to {out}")
    finally:
        ppt.Quit()


if __name__ == "__main__":
    main()
