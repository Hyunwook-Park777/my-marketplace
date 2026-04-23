#!/usr/bin/env python3
"""
PDF vs MD Conversion Quality Verification

PDF 원본과 변환된 Markdown을 비교하여 변환 품질을 0~100점으로 평가합니다.
5개 카테고리(텍스트/이미지/표/수식/구조)를 가중 합산하여 종합 점수를 산출합니다.

Usage:
    # 단일 파일 비교
    python verify_conversion.py --pdf paper.pdf --md paper.md

    # 배치 비교 (폴더)
    python verify_conversion.py --pdf-dir ./pdfs/ --md-dir ./converted/ --output report.json

Requirements:
    pip install pymupdf  (fitz)
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def extract_pdf_metadata(pdf_path: Path) -> dict:
    """PyMuPDF로 PDF에서 메타데이터 추출"""
    try:
        import fitz
    except ImportError:
        return {
            "error": "pymupdf not installed. Install with: pip install pymupdf",
            "page_count": 0,
            "total_words": 0,
            "image_count": 0,
            "table_indicators": 0,
            "equation_indicators": 0,
            "has_toc": False,
            "toc_entries": 0
        }

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return {"error": str(e)}

    page_count = len(doc)
    total_words = 0
    image_count = 0
    full_text = ""
    is_scanned = False

    for page in doc:
        text = page.get_text()
        full_text += text + "\n"
        words = text.split()
        total_words += len(words)

        images = page.get_images(full=True)
        image_count += len(images)

    doc.close()

    # 스캔 PDF 감지: 페이지 수 대비 텍스트가 극도로 적음
    if page_count > 0 and total_words / page_count < 10:
        is_scanned = True

    # 표 추정: "Table N", "Tab. N", "TABLE N" 패턴
    table_patterns = re.findall(
        r'(?i)\b(?:table|tab\.?)\s+\d+', full_text
    )
    table_indicators = len(set(table_patterns))

    # 수식 추정: "(N)" 수식 번호 패턴 (문장 끝에 위치)
    equation_patterns = re.findall(
        r'(?<=[.)\s])\(\d{1,3}\)\s*$', full_text, re.MULTILINE
    )
    equation_indicators = len(equation_patterns)

    # TOC 추출
    try:
        toc = fitz.open(str(pdf_path)).get_toc()
        has_toc = len(toc) > 0
        toc_entries = len(toc)
    except Exception:
        has_toc = False
        toc_entries = 0

    return {
        "page_count": page_count,
        "total_words": total_words,
        "image_count": image_count,
        "table_indicators": table_indicators,
        "equation_indicators": equation_indicators,
        "has_toc": has_toc,
        "toc_entries": toc_entries,
        "is_scanned": is_scanned
    }


def extract_md_metadata(md_path: Path) -> dict:
    """Markdown 파일에서 메타데이터 추출"""
    content = md_path.read_text(encoding="utf-8")

    # 단어 수
    text_only = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', content)  # 이미지 제거
    text_only = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', text_only)  # 링크 텍스트만
    text_only = re.sub(r'[#|*_`~>]', '', text_only)  # MD 문법 제거
    text_only = re.sub(r'<[^>]+>', '', text_only)  # HTML 태그 제거
    text_only = re.sub(r'\$\$.*?\$\$', '', text_only, flags=re.DOTALL)  # 블록 수식 제거
    text_only = re.sub(r'\$[^$]+\$', '', text_only)  # 인라인 수식 제거
    words = text_only.split()
    total_words = len(words)

    # 헤딩 수
    headings = re.findall(r'^#{1,6}\s+.+$', content, re.MULTILINE)
    heading_count = len(headings)

    # 이미지 참조
    image_refs_raw = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', content)
    image_refs = len(image_refs_raw)

    # 실제 존재하는 이미지 파일 수
    md_dir = md_path.parent
    image_files_found = 0
    for ref in image_refs_raw:
        clean_ref = ref.strip('<>') if ref.startswith('<') and ref.endswith('>') else ref
        if not clean_ref.startswith(('http://', 'https://')):
            img_path = md_dir / clean_ref
            if img_path.exists():
                image_files_found += 1

    # MD 표 카운트 (구분선 |---|---| 패턴)
    table_separators = re.findall(r'^\|[\s\-:|]+\|$', content, re.MULTILINE)
    table_count = len(table_separators)

    # 수식 카운트
    block_equations = re.findall(r'\$\$.*?\$\$', content, re.DOTALL)
    block_eq_count = len(block_equations)
    # 인라인 수식: $...$ ($$로 시작하지 않는 것)
    inline_equations = re.findall(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', content)
    inline_eq_count = len(inline_equations)

    return {
        "total_words": total_words,
        "heading_count": heading_count,
        "image_refs": image_refs,
        "image_files_found": image_files_found,
        "table_count": table_count,
        "inline_eq_count": inline_eq_count,
        "block_eq_count": block_eq_count
    }


def _score_ratio(actual: int, expected: int, perfect_threshold: float = 1.0) -> float:
    """비율 기반 점수 산출 (0~100)"""
    if expected == 0:
        return 100.0 if actual == 0 else 80.0  # 기대값 0이면 이 카테고리는 N/A
    ratio = actual / expected
    if ratio >= perfect_threshold:
        return 100.0
    elif ratio >= perfect_threshold * 0.82:
        return 70.0
    elif ratio >= perfect_threshold * 0.59:
        return 40.0
    else:
        return 10.0


def compare_pdf_md(pdf_meta: dict, md_meta: dict) -> dict:
    """PDF와 MD 메타데이터를 비교하여 5개 카테고리별 점수 산출

    카테고리별 가중치:
        텍스트 완전성: 40%
        이미지 완전성: 25%
        표 완전성: 15%
        수식 완전성: 10%
        구조 품질: 10%
    """
    if pdf_meta.get("error"):
        return {
            "error": pdf_meta["error"],
            "overall_score": 0,
            "verdict": "error"
        }

    issues = []
    recommendations = []

    # 스캔 PDF 경고
    if pdf_meta.get("is_scanned"):
        issues.append("Scanned PDF detected: text extraction may be incomplete")
        recommendations.append("Consider using OCR mode (--method ocr) for better results")

    # 1. 텍스트 완전성 (40%)
    # PDF 헤더/푸터/페이지번호는 MD에서 제거되므로 85%를 100점 기준
    text_ratio = md_meta["total_words"] / max(pdf_meta["total_words"], 1)
    if text_ratio >= 0.85:
        text_score = 100.0
    elif text_ratio >= 0.70:
        text_score = 70.0 + (text_ratio - 0.70) / 0.15 * 30.0
    elif text_ratio >= 0.50:
        text_score = 40.0 + (text_ratio - 0.50) / 0.20 * 30.0
    else:
        text_score = max(5.0, text_ratio / 0.50 * 40.0)

    text_detail = {
        "score": round(text_score, 1),
        "pdf_words": pdf_meta["total_words"],
        "md_words": md_meta["total_words"],
        "ratio": round(text_ratio, 3),
        "note": "MD/PDF word ratio (0.85+ = full score, accounts for headers/footers removal)"
    }

    if text_ratio < 0.70:
        issues.append(f"Low text completeness: {text_ratio:.1%} of PDF words found in MD")
        recommendations.append("Check if MinerU missed pages or sections")

    # 2. 이미지 완전성 (25%)
    image_score = _score_ratio(md_meta["image_refs"], pdf_meta["image_count"])
    image_detail = {
        "score": round(image_score, 1),
        "pdf_images": pdf_meta["image_count"],
        "md_image_refs": md_meta["image_refs"],
        "md_image_files_found": md_meta["image_files_found"],
        "note": "MD image references / PDF embedded images"
    }

    if pdf_meta["image_count"] > 0 and md_meta["image_refs"] == 0:
        issues.append(f"No images found in MD (PDF has {pdf_meta['image_count']} images)")
        recommendations.append("Run verify_figures.py --mode repair to recover images")
    elif md_meta["image_refs"] > 0 and md_meta["image_files_found"] < md_meta["image_refs"]:
        broken = md_meta["image_refs"] - md_meta["image_files_found"]
        issues.append(f"{broken} image reference(s) point to missing files")

    # 3. 표 완전성 (15%)
    table_score = _score_ratio(md_meta["table_count"], pdf_meta["table_indicators"])
    table_detail = {
        "score": round(table_score, 1),
        "pdf_table_indicators (estimated)": pdf_meta["table_indicators"],
        "md_tables": md_meta["table_count"],
        "note": "PDF table count is estimated from 'Table N' captions"
    }

    if pdf_meta["table_indicators"] > 0 and md_meta["table_count"] == 0:
        issues.append(f"No tables found in MD (PDF has ~{pdf_meta['table_indicators']} tables)")
        recommendations.append("Check if tables were converted as HTML and need post-processing")

    # 4. 수식 완전성 (10%)
    md_total_eq = md_meta["inline_eq_count"] + md_meta["block_eq_count"]
    equation_score = _score_ratio(md_total_eq, pdf_meta["equation_indicators"])
    equation_detail = {
        "score": round(equation_score, 1),
        "pdf_equation_indicators (estimated)": pdf_meta["equation_indicators"],
        "md_inline_equations": md_meta["inline_eq_count"],
        "md_block_equations": md_meta["block_eq_count"],
        "note": "PDF equation count is estimated from '(N)' numbering patterns"
    }

    # 5. 구조 품질 (10%)
    if pdf_meta["toc_entries"] > 0:
        structure_score = _score_ratio(
            md_meta["heading_count"], pdf_meta["toc_entries"]
        )
    else:
        # TOC 없으면 헤딩이 존재하기만 하면 OK
        structure_score = 100.0 if md_meta["heading_count"] > 0 else 30.0

    structure_detail = {
        "score": round(structure_score, 1),
        "pdf_toc_entries": pdf_meta["toc_entries"],
        "md_headings": md_meta["heading_count"],
        "note": "MD headings / PDF TOC entries"
    }

    # 가중 합산
    overall = (
        text_score * 0.40 +
        image_score * 0.25 +
        table_score * 0.15 +
        equation_score * 0.10 +
        structure_score * 0.10
    )

    # 판정
    if overall >= 85:
        verdict = "good"
    elif overall >= 60:
        verdict = "acceptable"
    else:
        verdict = "poor"

    return {
        "overall_score": round(overall, 1),
        "verdict": verdict,
        "text_completeness": text_detail,
        "image_completeness": image_detail,
        "table_completeness": table_detail,
        "equation_completeness": equation_detail,
        "structure_quality": structure_detail,
        "issues": issues,
        "recommendations": recommendations
    }


def verify_single(pdf_path: Path, md_path: Path) -> dict:
    """단일 PDF-MD 쌍 검증"""
    pdf_meta = extract_pdf_metadata(pdf_path)
    md_meta = extract_md_metadata(md_path)

    comparison = compare_pdf_md(pdf_meta, md_meta)

    return {
        "pdf": str(pdf_path),
        "md": str(md_path),
        "pdf_metadata": pdf_meta,
        "md_metadata": md_meta,
        **comparison
    }


def verify_batch(pdf_dir: Path, md_dir: Path) -> dict:
    """배치 PDF-MD 검증"""
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    md_files = {f.stem: f for f in md_dir.glob("*.md")}

    results = []
    scores = []
    good_count = 0
    acceptable_count = 0
    poor_count = 0
    error_count = 0

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        md_path = md_files.get(stem)

        if md_path is None:
            # 대소문자 무시 매칭
            for md_stem, md_p in md_files.items():
                if md_stem.lower() == stem.lower():
                    md_path = md_p
                    break

        if md_path is None:
            results.append({
                "pdf": str(pdf_path),
                "md": None,
                "overall_score": 0,
                "verdict": "missing_md",
                "issues": [f"No matching MD file found for {pdf_path.name}"]
            })
            error_count += 1
            print(f"  SKIP: {pdf_path.name} (no matching MD)")
            continue

        print(f"  Verifying: {pdf_path.name} <-> {md_path.name}")
        result = verify_single(pdf_path, md_path)
        results.append(result)

        score = result.get("overall_score", 0)
        verdict = result.get("verdict", "error")
        scores.append(score)

        if verdict == "good":
            good_count += 1
        elif verdict == "acceptable":
            acceptable_count += 1
        elif verdict == "poor":
            poor_count += 1
        else:
            error_count += 1

        print(f"    Score: {score:.1f} ({verdict})")

    average_score = sum(scores) / len(scores) if scores else 0

    return {
        "summary": {
            "total_files": len(pdf_files),
            "good": good_count,
            "acceptable": acceptable_count,
            "poor": poor_count,
            "error": error_count,
            "average_score": round(average_score, 1)
        },
        "files": results,
        "timestamp": datetime.now().isoformat()
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify PDF to Markdown conversion quality"
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="Single PDF file path"
    )
    parser.add_argument(
        "--md",
        type=Path,
        default=None,
        help="Single MD file path"
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=None,
        help="Directory containing original PDF files (batch mode)"
    )
    parser.add_argument(
        "--md-dir",
        type=Path,
        default=None,
        help="Directory containing converted MD files (batch mode)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON report path (default: verification_report.json)"
    )

    args = parser.parse_args()

    # 단일 모드
    if args.pdf and args.md:
        if not args.pdf.exists():
            print(f"Error: PDF not found: {args.pdf}")
            return 1
        if not args.md.exists():
            print(f"Error: MD not found: {args.md}")
            return 1

        print(f"=== Conversion Quality Verification ===\n")
        print(f"PDF: {args.pdf}")
        print(f"MD:  {args.md}\n")

        result = verify_single(args.pdf, args.md)

        print(f"Overall Score: {result['overall_score']:.1f}/100 ({result['verdict']})")
        print(f"  Text:      {result['text_completeness']['score']:.1f}/100")
        print(f"  Images:    {result['image_completeness']['score']:.1f}/100")
        print(f"  Tables:    {result['table_completeness']['score']:.1f}/100")
        print(f"  Equations: {result['equation_completeness']['score']:.1f}/100")
        print(f"  Structure: {result['structure_quality']['score']:.1f}/100")

        if result.get("issues"):
            print(f"\nIssues:")
            for issue in result["issues"]:
                print(f"  - {issue}")

        if result.get("recommendations"):
            print(f"\nRecommendations:")
            for rec in result["recommendations"]:
                print(f"  - {rec}")

        output_path = args.output or Path("verification_report.json")
        report = {"files": [result], "summary": {"total_files": 1, "average_score": result["overall_score"]}}

    # 배치 모드
    elif args.pdf_dir and args.md_dir:
        if not args.pdf_dir.exists():
            print(f"Error: PDF directory not found: {args.pdf_dir}")
            return 1
        if not args.md_dir.exists():
            print(f"Error: MD directory not found: {args.md_dir}")
            return 1

        print(f"=== Batch Conversion Quality Verification ===\n")
        print(f"PDF dir: {args.pdf_dir}")
        print(f"MD dir:  {args.md_dir}\n")

        report = verify_batch(args.pdf_dir, args.md_dir)

        print(f"\n{'='*50}")
        print(f"Summary:")
        print(f"  Total: {report['summary']['total_files']}")
        print(f"  Good (>=85):       {report['summary']['good']}")
        print(f"  Acceptable (60-84): {report['summary']['acceptable']}")
        print(f"  Poor (<60):        {report['summary']['poor']}")
        print(f"  Error/Missing:     {report['summary']['error']}")
        print(f"  Average Score:     {report['summary']['average_score']:.1f}/100")

        output_path = args.output or Path("verification_report.json")

    else:
        parser.error("Provide either (--pdf + --md) or (--pdf-dir + --md-dir)")
        return 1

    # 리포트 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nReport saved: {output_path}")

    # 종료 코드
    avg = report.get("summary", {}).get("average_score", 0)
    if avg >= 85:
        return 0
    elif avg >= 60:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit(main())
