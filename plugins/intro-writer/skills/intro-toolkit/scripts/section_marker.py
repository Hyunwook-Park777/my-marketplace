#!/usr/bin/env python3
"""
Section Marker - 변환된 논문 MD 에 섹션 경계 마커를 삽입 (비파괴, 멱등)

pdf-converter 가 만든 MD 의 헤딩을 읽어 표준 섹션(Abstract, Introduction,
Methods, Results, Discussion, Conclusion, References)을 판별하고
<!-- SECTION_START: X --> / <!-- SECTION_END: X --> 주석만 추가한다.
본문·헤딩·DOI·URL 은 한 글자도 지우거나 바꾸지 않는다.

MinerU 는 소제목까지 모두 `#` 하나로 내보내는 경우가 많아, 헤딩 수준이 아니라
헤딩 문구와 등장 순서로 판단한다:
  - 강한 일치 (헤딩 전체가 "Introduction", "2. Results and discussion" 등) → 언제나 전환
  - 약한 일치 (헤딩에 "experimental", "simulation" 등 키워드 포함) → 논문 순서상 앞으로만 전환
    (Results 안의 "Validation of CFD simulation" 이 Methods 로 되돌아가지 않도록)
  - 그 외 헤딩 → 현재 섹션의 소제목

Usage:
    python section_marker.py --input-dir ./md_converted/
    python section_marker.py --single ./md_converted/paper.md
    python section_marker.py --input-dir ./md_converted/ --report ./md_converted/section_report.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ORDER = ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion", "References"]

# 헤딩 전체가 이 형태면 강한 일치
STRONG = [
    ("Abstract", r"abstract|summary"),
    ("Introduction", r"introduction|background|introduction and background"),
    ("Methods", r"(materials?\s*(and|&)\s*)?methods?|methodology|experimental( (setup|set-up|method(s|ology)?|details|procedure|apparatus))?|experiments?|experiments? (and|&) methods?|experimental (and|&) numerical (setup|methods?)"),
    ("Results", r"results?|results?\s*(and|&)\s*discussions?"),
    ("Discussion", r"discussions?"),
    ("Conclusion", r"conclusions?|concluding remarks|summary and conclusions?|conclusions? and (outlook|future work)"),
    ("References", r"references?|bibliography|literature cited"),
    ("Other", r"highlights|article\s*info(rmation)?|keywords?|nomenclature|abbreviations|acknowledge?ments?|appendix.*|declaration.*|credit authorship.*|data availability.*|supplementary.*|supporting information|funding|author contributions?|conflicts? of interest"),
]

# 헤딩에 포함되면 약한 일치 (앞으로만 전환)
WEAK = [
    ("Methods", r"\b(method|methodology|experimental|experiment|setup|set-up|apparatus|test bench|test rig|modell?ing|numerical|simulation|computational|materials)\b"),
    ("Results", r"\bresults?\b"),
    ("Conclusion", r"\bconclu"),
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
MARKER_RE = re.compile(r"^<!-- SECTION_(START|END): \w+ -->\s*$")
# "2.", "2.1.", "3 ", "IV.", "a)" — 글자 하나 뒤 공백("a b s t r a c t")은 번호가 아니다
NUMBER_PREFIX = re.compile(r"^(\d+(\.\d+)*\.?|[ivxlc]+\.|[a-z][.)])\s+", re.IGNORECASE)


def clean_heading(text: str) -> str:
    text = re.sub(r"[*_`]", "", text).strip()
    text = NUMBER_PREFIX.sub("", text)
    text = text.strip(" .:")
    return re.sub(r"\s+", " ", text).lower()


SUBNUM_RE = re.compile(r"^\s*[*_`]*(\d+)\.\d+")
INTRO, METHODS = ORDER.index("Introduction"), ORDER.index("Methods")


def classify(heading: str, rank: int, intro_major: str | None) -> str | None:
    """rank: 마지막 본 표준 섹션의 순위 (Other 는 순위를 바꾸지 않는다)."""
    h = clean_heading(heading)
    squashed = h.replace(" ", "")
    for name, pat in STRONG:
        if re.fullmatch(pat, h) or re.fullmatch(pat.replace(r"\s*", "").replace(" ", ""), squashed):
            # 논문 끝의 "Summary" 는 초록이 아니라 결론, Methods 안의 "Background" 는 소제목
            if name == "Abstract" and h == "summary" and rank >= INTRO:
                return "Conclusion" if rank > INTRO else None
            if name == "Introduction" and h == "background" and rank >= METHODS:
                return None
            return name
    # 약한 일치는 Introduction 이후에만 — 논문 제목("Experimental investigation of ...")을 Methods 로 오인하지 않도록
    if rank < INTRO:
        return None
    # "1.1 Numerical studies in literature" 처럼 Introduction 번호의 하위 절이면 Introduction 소제목
    sub = SUBNUM_RE.match(heading)
    if rank == INTRO and sub and intro_major and sub.group(1) == intro_major:
        return None
    for name, pat in WEAK:
        if re.search(pat, h) and ORDER.index(name) > rank:
            return name
    return None


def mark(content: str) -> tuple[str, list[str]]:
    nl = "\r\n" if "\r\n" in content else "\n"
    lines = [ln for ln in content.split(nl) if not MARKER_RE.match(ln)]
    out, found = [], []
    current, rank, intro_major = None, -1, None
    fence = None
    for ln in lines:
        stripped = ln.lstrip()
        for f in ("```", "~~~"):
            if stripped.startswith(f):
                fence = None if fence == f else (fence or f)
        m = None if fence else HEADING_RE.match(ln)
        if m:
            section = classify(m.group(2), rank, intro_major)
            if section and section != current:
                if current:
                    out.append(f"<!-- SECTION_END: {current} -->")
                current = section
                if section != "Other":
                    found.append(section)
                    rank = ORDER.index(section)
                    if section == "Introduction":
                        num = re.match(r"^\s*[*_`]*(\d+)[.\s]", m.group(2))
                        intro_major = num.group(1) if num else "1"
                out.append(f"<!-- SECTION_START: {section} -->")
        out.append(ln)
    if current:
        out.append(f"<!-- SECTION_END: {current} -->")
    return nl.join(out), list(dict.fromkeys(found))


def process(path: Path) -> dict:
    with open(path, encoding="utf-8", newline="") as f:  # 줄바꿈(CRLF/LF)을 그대로 보존
        text = f.read()
    marked, found = mark(text)
    if marked != text:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(marked)
    missing = [s for s in ("Abstract", "Introduction") if s not in found]
    return {"file": path.name, "sections_found": found, "missing_core": missing,
            "status": "ok" if not missing else "warning"}


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows cp949 콘솔에서 파일명의 –, ₂ 등으로 중단되지 않도록
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Insert SECTION_START/END markers into paper MD files (in place, non-destructive)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--input-dir", type=Path)
    g.add_argument("--single", type=Path)
    ap.add_argument("--report", type=Path, help="write per-file JSON report here")
    args = ap.parse_args()

    if args.single:
        files = [args.single]
    else:
        files = sorted(p for p in args.input_dir.glob("*.md")
                       if not p.name.startswith("_") and "_backup_" not in p.name)
    if not files:
        print("No MD files found", file=sys.stderr)
        sys.exit(1)

    results = [process(f) for f in files]
    report = {"total": len(results),
              "warnings": sum(r["status"] == "warning" for r in results),
              "files": results}
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        flag = "" if r["status"] == "ok" else f"  [missing: {', '.join(r['missing_core'])}]"
        print(f"{r['file']}: {', '.join(r['sections_found']) or '(none)'}{flag}")
    print(f"\n{report['total']} files, {report['warnings']} with missing Abstract/Introduction")


if __name__ == "__main__":
    main()
