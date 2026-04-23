#!/usr/bin/env python3
"""
Equation Fixer: Restore equation numbers (and arrows) lost in MinerU conversion.

PDF → MinerU로 변환된 Markdown 에서 자주 누락되는 두 가지를 복원한다.

1) 식 번호 `(N.N.N)` 누락
   MinerU 의 pipeline / txt 모드는 display 수식 오른쪽에 붙은 번호 `(1.1.8)` 를
   layout 분석에서 드롭하는 경우가 많다. 이 스크립트는 PDF 원문에서 `(N.N.N)`
   위치를 찾고, 바로 앞 문단/수식의 텍스트를 키로 삼아 MD 의 display 수식과
   순서/유사도 기반으로 짝지어 `\\tag{N.N.N}` 을 삽입한다.

2) 화살표 `→`, `⇌`, `↔` 등이 공백으로 변환된 경우
   MinerU 가 일부 화살표 유니코드를 놓치면 MD 수식 내부에 `e  H` 처럼 연속 2 칸
   공백만 남는다. PDF 해당 위치에 화살표가 있었고 MD 에 대응 LaTeX 명령
   (`\\to`, `\\rightarrow`, `\\rightleftharpoons` 등) 이 없으면, 한 번에 한
   후보만 조심스럽게 `\\rightarrow` 로 치환한다 (false positive 방지).

Usage:
    python equation_fixer.py --pdf input.pdf --md output.md
    python equation_fixer.py --pdf-dir ./pdfs/ --md-dir ./md_output/

Requirements:
    pip install pymupdf
"""

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# PyMuPDF import with Device Guard fallback
# ---------------------------------------------------------------------------
def _import_pymupdf():
    """Import PyMuPDF, preferring `pymupdf` over `fitz` shim (some Windows
    Device Guard environments block the `fitz` shim DLL)."""
    try:
        import pymupdf  # type: ignore
        return pymupdf
    except ImportError:
        try:
            import fitz  # type: ignore
            return fitz
        except ImportError as exc:
            raise ImportError("PyMuPDF not installed. Run: pip install pymupdf") from exc


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class PdfEquationLabel:
    number: str              # e.g. "1.1.8"
    preceding_text: str      # up to 300 chars of text before the "(N.N.N)"
    body_text: str           # raw text of the equation body (up to ~300 chars before number, math-ish lines only)
    body_signature: str      # canonicalised signature of the body for matching
    has_arrow: bool          # True if a unicode arrow char appears just before


@dataclass
class MdDisplayEquation:
    index: int               # 0-based index among display equations in MD
    start: int               # char offset in MD of the opening $$
    end: int                 # char offset in MD of the closing $$ + 1 (exclusive)
    body: str                # content between the two $$ lines
    body_signature: str      # canonicalised signature of the body for matching
    preceding_text: str      # ~300 chars of preceding plain text
    has_tag: bool            # already tagged (has \tag{...})
    has_arrow_cmd: bool      # has \to / \rightarrow / \rightleftharpoons / \xrightarrow


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------
ARROW_CHARS = "→⇌↔⇋←⇐⇒↦↣↠↪↩"

EQ_NUMBER_RE = re.compile(r"\((\d+\.\d+\.\d+[a-z]?)\)")


def extract_pdf_equation_labels(pdf_path: Path) -> List[PdfEquationLabel]:
    """Scan PDF in page order and extract every `(N.N.N)` equation label
    with the surrounding prose context AND a canonical signature of the
    equation body that precedes the label.

    We walk the page's layout blocks (via PyMuPDF ``get_text("blocks")``)
    so the equation body — typically a short block right above or to the
    left of the label — can be isolated cleanly from adjacent prose.
    """
    pymupdf = _import_pymupdf()
    doc = pymupdf.open(str(pdf_path))
    labels: List[PdfEquationLabel] = []
    try:
        for page in doc:
            blocks = page.get_text("blocks")  # list of (x0,y0,x1,y1,text,...)
            full_text = page.get_text()
            # Build index: (start_char_in_full_text, block_text)
            search_cursor = 0
            block_spans = []
            for b in blocks:
                btxt = b[4]
                pos = full_text.find(btxt, search_cursor)
                if pos < 0:
                    pos = full_text.find(btxt)
                block_spans.append((pos if pos >= 0 else search_cursor,
                                    pos + len(btxt) if pos >= 0 else search_cursor,
                                    btxt))
                if pos >= 0:
                    search_cursor = pos + len(btxt)

            for match in EQ_NUMBER_RE.finditer(full_text):
                before = full_text[max(0, match.start() - 400): match.start()]
                preceding = _normalize_whitespace(before)
                body_text = _extract_pdf_body_from_blocks(
                    match.start(), block_spans, before
                )
                body_sig = _canonicalize_body(body_text)
                has_arrow = any(ch in body_text for ch in ARROW_CHARS) or \
                            any(ch in before[-80:] for ch in ARROW_CHARS)
                labels.append(PdfEquationLabel(
                    number=match.group(1),
                    preceding_text=preceding,
                    body_text=body_text,
                    body_signature=body_sig,
                    has_arrow=has_arrow,
                ))
    finally:
        doc.close()
    return labels


def _extract_pdf_body_from_blocks(
    label_pos: int,
    block_spans: List[Tuple[int, int, str]],
    fallback_before: str,
) -> str:
    """Locate the block that contains the `(N.N.N)` label and return the
    preceding short blocks that look like equation bodies.

    An equation body block is typically (a) shorter than 120 chars and
    (b) dominated by symbols/digits rather than English words.
    """
    containing_idx = None
    for i, (s, e, _t) in enumerate(block_spans):
        if s <= label_pos < e:
            containing_idx = i
            break
    if containing_idx is None:
        return fallback_before[-160:].strip()

    bodies: List[str] = []
    # Include text from the label's own block (trim off the "(N.N.N)")
    own_text = block_spans[containing_idx][2]
    own_text = EQ_NUMBER_RE.sub("", own_text).strip()
    if own_text and _looks_like_eq_body(own_text):
        bodies.append(own_text)
    # Walk backwards for adjacent math-heavy blocks, up to 2
    for j in range(containing_idx - 1, max(containing_idx - 4, -1), -1):
        btxt = block_spans[j][2].strip()
        if not btxt:
            continue
        if _looks_like_eq_body(btxt):
            bodies.append(btxt)
        if len(bodies) >= 2:
            break
    return " ".join(reversed(bodies))[-200:]


def _looks_like_eq_body(text: str) -> bool:
    """Heuristic: a PDF text block that looks like an equation body."""
    text = text.strip()
    if not text or len(text) > 160:
        return False
    # Count "long" (>=5) English-looking words
    long_words = re.findall(r"[A-Za-z]{5,}", text)
    real_prose = [w for w in long_words
                  if sum(1 for c in w if c.islower()) >= max(3, int(0.7 * len(w)))]
    return len(real_prose) <= 2


def _canonicalize_body(text: str) -> str:
    """Reduce an equation body to a comparable signature.

    Drops whitespace, LaTeX commands, braces, brackets, prior equation
    labels, and rare unicode decorations. Lowercases everything and keeps
    only letters/digits plus a few operator characters. The same
    canonicalisation is applied to both PDF-extracted bodies and MD
    `$$...$$` bodies, which lets us compare them reliably even though
    MinerU renders them very differently.
    """
    # Remove embedded equation labels like "(1.1.4)" that survive in PDF
    # extractions of adjacent equations
    text = re.sub(r"\(\s*\d+\.\d+\.\d+[a-z]?\s*\)", "", text)
    # LaTeX commands (e.g. \mathrm, \frac, \rightarrow) — strip the command
    # name; the `{args}` that follow are handled by the brace cleanup below
    text = re.sub(r"\\[A-Za-z]+", "", text)
    # Sub/super-script braces become linear
    text = re.sub(r"[{}\[\]]", "", text)
    # Collapse arrows (any unicode arrow) to a single '>' token
    for ch in ARROW_CHARS:
        text = text.replace(ch, ">")
    # Remove quotes/ticks and redundant punctuation
    text = re.sub(r"[\s`'\"~]", "", text)
    # Keep only the symbols that survive well in PDFs AND MinerU output
    text = re.sub(r"[^A-Za-z0-9+\-/,=><]", "", text)
    return text.lower()


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# MD parsing
# ---------------------------------------------------------------------------
DISPLAY_EQ_RE = re.compile(r"\$\$\s*\n(.*?)\n\s*\$\$", re.DOTALL)
ARROW_CMD_RE = re.compile(
    r"\\(to|rightarrow|longrightarrow|leftarrow|leftrightarrow|"
    r"rightleftharpoons|xrightarrow|xleftarrow|leftrightharpoons)\b"
)
TAG_RE = re.compile(r"\\tag\{")


def find_display_equations(md_text: str) -> List[MdDisplayEquation]:
    """Return all display equations in the MD with body signature and context."""
    equations: List[MdDisplayEquation] = []
    for i, m in enumerate(DISPLAY_EQ_RE.finditer(md_text)):
        body = m.group(1)
        before = md_text[max(0, m.start() - 400): m.start()]
        before_clean = _strip_md_markup(before)
        equations.append(MdDisplayEquation(
            index=i,
            start=m.start(),
            end=m.end(),
            body=body,
            body_signature=_canonicalize_body(body),
            preceding_text=_normalize_whitespace(before_clean),
            has_tag=bool(TAG_RE.search(body)),
            has_arrow_cmd=bool(ARROW_CMD_RE.search(body)),
        ))
    return equations


def _strip_md_markup(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)        # images
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)     # links
    text = re.sub(r"[`*_~>#|]", "", text)                    # md accent chars
    text = re.sub(r"\$\$[^$]*\$\$", " ", text, flags=re.DOTALL)  # prior display math
    text = re.sub(r"(?<!\$)\$[^$\n]+\$(?!\$)", " ", text)    # inline math
    text = re.sub(r"<[^>]+>", " ", text)                     # html
    return text


# ---------------------------------------------------------------------------
# Matching (PDF labels <-> MD display equations)
# ---------------------------------------------------------------------------
def match_labels_to_equations(
    labels: List[PdfEquationLabel],
    equations: List[MdDisplayEquation],
    md_text: str,
    similarity_threshold: float = 0.55,
) -> List[Tuple[PdfEquationLabel, Optional[MdDisplayEquation], float]]:
    """Match PDF equation labels to MD display equations.

    Strategy: **body-signature similarity** plus monotone ordering.

    For each PDF label (in document order), find the best-matching
    unassigned MD display equation within a forward window by comparing
    canonicalised equation bodies (letters/digits/operators only, no
    LaTeX commands). This is robust to how aggressively MinerU reshapes
    math into `\\mathrm{...}` with spaces, because the signature drops
    both.

    Falls back to preceding-text fuzzy similarity when the body
    signature is too short to be discriminative.
    """
    results: List[Tuple[PdfEquationLabel, Optional[MdDisplayEquation], float]] = []
    last_used_eq_idx = -1
    window_size = 20

    for label in labels:
        assigned: Optional[MdDisplayEquation] = None
        score = 0.0
        best_idx: Optional[int] = None
        best_score = 0.0

        # Restrict search to the forward window
        start_idx = last_used_eq_idx + 1
        short_label = len(label.body_signature) < 10
        for eq in equations[start_idx:start_idx + window_size]:
            if eq.has_tag:
                continue
            # Body-signature similarity
            body_score = _similarity(label.body_signature, eq.body_signature)
            # Boost for substring containment either way
            if label.body_signature and eq.body_signature:
                if label.body_signature[:16] and label.body_signature[:16] in eq.body_signature:
                    body_score = max(body_score, 0.85)
                elif eq.body_signature[:16] and eq.body_signature[:16] in label.body_signature:
                    body_score = max(body_score, 0.85)
            # Preceding text similarity
            ctx_score = _similarity(
                label.preceding_text[-160:],
                eq.preceding_text[-160:],
            )
            # Weighting: when the body signature is very short (a few symbols,
            # e.g. σ^s = σ^i + σ^d = -σ^M), the math alone is not
            # discriminative, so lean harder on the preceding-paragraph text.
            short_eq = len(eq.body_signature) < 10
            if short_label or short_eq:
                combined = 0.35 * body_score + 0.65 * ctx_score
            else:
                combined = 0.75 * body_score + 0.25 * ctx_score
            if combined > best_score:
                best_score = combined
                best_idx = eq.index

        if best_idx is not None and best_score >= similarity_threshold:
            assigned = equations[best_idx]
            score = best_score
            last_used_eq_idx = assigned.index

        results.append((label, assigned, score))

    return results


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Rewriting
# ---------------------------------------------------------------------------
def apply_tags(
    md_text: str,
    matches: List[Tuple[PdfEquationLabel, Optional[MdDisplayEquation], float]],
    restore_arrows: bool = True,
) -> Tuple[str, dict]:
    """Rewrite MD text so each matched display equation carries a \\tag{N.N.N}.

    Applies replacements from last to first so the earlier offsets remain
    valid. Returns the new text and a statistics dict suitable for a report.
    """
    edits: List[Tuple[int, int, str]] = []  # (start, end, replacement)
    tagged = 0
    arrow_fixes = 0

    for label, eq, score in matches:
        if eq is None:
            continue
        body = eq.body.rstrip()
        # Skip if already tagged (defensive)
        if TAG_RE.search(body):
            continue
        new_body = body
        if restore_arrows and label.has_arrow and not eq.has_arrow_cmd:
            new_body, changed = _restore_arrow(new_body)
            if changed:
                arrow_fixes += 1
        new_block = f"$$\n{new_body} \\tag{{{label.number}}}\n$$"
        edits.append((eq.start, eq.end, new_block))
        tagged += 1

    # Apply last-to-first
    new_text = md_text
    for start, end, replacement in sorted(edits, key=lambda e: e[0], reverse=True):
        new_text = new_text[:start] + replacement + new_text[end:]

    stats = {
        "labels_in_pdf": len(matches),
        "matched": tagged,
        "unmatched": sum(1 for _, eq, _ in matches if eq is None),
        "arrow_restorations": arrow_fixes,
    }
    return new_text, stats


# Pattern: two or more consecutive ASCII spaces between two math tokens
DOUBLE_SPACE_RE = re.compile(r"(\S)(  +)(\S)")


def _restore_arrow(math_body: str) -> Tuple[str, bool]:
    """Conservatively insert `\\rightarrow` (or `\\xrightarrow`) where MinerU
    dropped the arrow character. Only fires in unambiguous cases.
    """
    # Case 1: `\stackrel{label}{ }` — MinerU knew an arrow was there but could
    # not identify the character. Convert to `\xrightarrow{label}`.
    fixed = re.sub(
        r"\\stackrel\s*\{([^{}]*)\}\s*\{\s*\}",
        r"\\xrightarrow{\1}",
        math_body,
    )
    if fixed != math_body:
        return fixed, True

    # Case 2: exactly one "two-space gap between tokens" in the body.
    # Multiple gaps are ambiguous and left alone.
    gaps = list(DOUBLE_SPACE_RE.finditer(math_body))
    if len(gaps) == 1:
        g = gaps[0]
        return math_body[:g.start(2)] + r" \rightarrow " + math_body[g.end(2):], True
    return math_body, False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def process_single(
    pdf_path: Path,
    md_path: Path,
    out_path: Optional[Path] = None,
    threshold: float = 0.35,
    restore_arrows: bool = True,
) -> dict:
    labels = extract_pdf_equation_labels(pdf_path)
    md_text = md_path.read_text(encoding="utf-8")
    equations = find_display_equations(md_text)
    matches = match_labels_to_equations(labels, equations, md_text, threshold)
    new_text, stats = apply_tags(md_text, matches, restore_arrows=restore_arrows)
    (out_path or md_path).write_text(new_text, encoding="utf-8")
    stats.update({
        "pdf": str(pdf_path),
        "md": str(md_path),
        "output": str(out_path or md_path),
        "display_equations_in_md": len(equations),
    })
    return stats


def process_batch(
    pdf_dir: Path,
    md_dir: Path,
    threshold: float = 0.35,
    restore_arrows: bool = True,
) -> dict:
    results = []
    summary = {"total": 0, "matched_total": 0, "arrow_total": 0, "skipped": 0}
    for md_file in sorted(md_dir.glob("*.md")):
        stem = md_file.stem
        pdf_candidate = pdf_dir / f"{stem}.pdf"
        if not pdf_candidate.exists():
            pdf_candidate = None
            for alt in pdf_dir.glob("*.pdf"):
                if alt.stem.lower() == stem.lower():
                    pdf_candidate = alt
                    break
        if pdf_candidate is None:
            summary["skipped"] += 1
            results.append({"md": str(md_file), "status": "no_matching_pdf"})
            continue
        r = process_single(pdf_candidate, md_file, None, threshold, restore_arrows)
        r["status"] = "ok"
        results.append(r)
        summary["total"] += 1
        summary["matched_total"] += r.get("matched", 0)
        summary["arrow_total"] += r.get("arrow_restorations", 0)
    return {"summary": summary, "files": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="Single PDF file")
    parser.add_argument("--md", type=Path, help="Single MD file to fix in place")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional output path (defaults to overwriting --md)")
    parser.add_argument("--pdf-dir", type=Path, help="Batch: directory of PDFs")
    parser.add_argument("--md-dir", type=Path, help="Batch: directory of MDs")
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="Context-similarity cutoff (0..1) for accepting a match")
    parser.add_argument("--no-arrows", action="store_true",
                        help="Skip heuristic arrow restoration")
    parser.add_argument("--report", type=Path, default=None,
                        help="Write JSON report to this path")

    args = parser.parse_args()

    if args.pdf and args.md:
        stats = process_single(args.pdf, args.md, args.output,
                               args.threshold, not args.no_arrows)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        if args.report:
            args.report.write_text(json.dumps(stats, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        sys.exit(0)
    if args.pdf_dir and args.md_dir:
        report = process_batch(args.pdf_dir, args.md_dir,
                               args.threshold, not args.no_arrows)
        print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
        if args.report:
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        sys.exit(0)

    parser.error("Provide either (--pdf + --md) or (--pdf-dir + --md-dir).")


if __name__ == "__main__":
    main()
