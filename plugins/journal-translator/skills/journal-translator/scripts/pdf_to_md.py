#!/usr/bin/env python3
"""
PDF to Markdown Converter using pymupdf4llm

PyMuPDF4LLM을 사용하여 PDF를 Markdown으로 변환하고 이미지를 추출합니다.

pymupdf4llm은 파일명에 공백/특수문자가 있으면 이미지 저장에 실패하므로,
짧은 임시 경로에서 변환 후 결과를 최종 위치로 이동합니다.

Usage:
    python pdf_to_md.py --input-dir ./papers/ --output-dir ./md_converted/
    python pdf_to_md.py --single ./paper.pdf --output-dir ./md_converted/

Requirements:
    pip install pymupdf4llm pymupdf
"""

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pymupdf
import pymupdf4llm


def convert_single_pdf(pdf_path: Path, output_dir: Path) -> dict:
    """단일 PDF를 Markdown으로 변환

    pymupdf4llm은 파일명의 공백/특수문자에 취약하므로,
    짧은 임시 디렉토리(C:/tmp/jt_xxx/)에서 변환 후 결과를 이동합니다.
    """
    stem = pdf_path.stem
    result = {
        "input": str(pdf_path),
        "output": None,
        "status": "pending",
        "pages": 0,
        "sections_found": [],
        "figures": 0,
        "tables": 0,
        "images_extracted": 0,
        "warnings": [],
        "error": None
    }

    tmp_dir = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        # 짧은 임시 디렉토리 생성
        short_hash = hashlib.md5(stem.encode()).hexdigest()[:8]
        tmp_dir = Path(f"C:/tmp/jt_{short_hash}")
        if tmp_dir.exists():
            shutil.rmtree(str(tmp_dir))
        tmp_dir.mkdir(parents=True)

        # 짧은 이름으로 PDF 복사
        safe_name = f"p{short_hash}"
        tmp_pdf = tmp_dir / f"{safe_name}.pdf"
        shutil.copy2(str(pdf_path), str(tmp_pdf))

        # 이미지 폴더 생성
        tmp_images = tmp_dir / safe_name / "images"
        tmp_images.mkdir(parents=True)

        # pymupdf4llm 변환
        md_text = pymupdf4llm.to_markdown(
            str(tmp_pdf),
            write_images=True,
            image_path=str(tmp_images),
            show_progress=False
        )

        # 임시 MD 저장
        tmp_md = tmp_dir / f"{safe_name}.md"
        tmp_md.write_text(md_text, encoding="utf-8")

        # 이미지 참조 경로를 원본 stem 기준으로 변환
        content = tmp_md.read_text(encoding="utf-8")

        # 임시 경로 → 원본 stem 경로로 치환
        tmp_img_path = str(tmp_images).replace("\\", "/")
        content = content.replace(tmp_img_path + "/", f"{stem}/images/")
        content = content.replace(tmp_img_path, f"{stem}/images")
        content = content.replace(f"{safe_name}/images/", f"{stem}/images/")

        # 최종 위치로 이동
        final_md = output_dir / f"{stem}.md"
        final_md.write_text(content, encoding="utf-8")

        # 이미지 폴더 이동
        final_images = output_dir / stem / "images"
        final_images.mkdir(parents=True, exist_ok=True)
        if tmp_images.exists():
            for img in tmp_images.iterdir():
                if img.is_file():
                    dest = final_images / img.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(img), str(dest))

        # 통계 수집
        result["output"] = str(final_md)
        result["status"] = "success"
        result["pages"] = len(pymupdf.open(str(pdf_path)))
        result["sections_found"] = extract_sections(content)
        result["figures"] = len(re.findall(r'!\[', content))
        result["tables"] = content.count('|---') + content.lower().count('<table')

        if final_images.exists():
            result["images_extracted"] = sum(
                1 for f in final_images.iterdir()
                if f.is_file() and f.suffix.lower() in
                ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
            )

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    return result


def extract_sections(content: str) -> list:
    """Markdown에서 섹션 헤더 추출"""
    sections = []
    section_patterns = [
        (r"#+\s*\.?\s*abstract", "Abstract"),
        (r"#+\s*\.?\s*introduction", "Introduction"),
        (r"#+\s*\.?\s*(materials?\s*(and|&)?\s*)?methods?", "Methods"),
        (r"#+\s*\.?\s*results?", "Results"),
        (r"#+\s*\.?\s*discussion", "Discussion"),
        (r"#+\s*\.?\s*conclusions?", "Conclusion"),
        (r"#+\s*\.?\s*references?", "References"),
    ]

    content_lower = content.lower()
    for pattern, section_name in section_patterns:
        if re.search(pattern, content_lower):
            sections.append(section_name)

    return sections


def batch_convert(input_dir: Path, output_dir: Path) -> dict:
    """폴더 내 모든 PDF를 변환"""
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(input_dir.glob("*.pdf"))

    if not pdf_files:
        return {"error": f"No PDF files found in {input_dir}",
                "summary": {"total": 0}}

    print(f"Found {len(pdf_files)} PDF files")
    print(f"Output: {output_dir}")
    print("-" * 50)

    results = []
    success = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Converting: {pdf_path.name}")
        r = convert_single_pdf(pdf_path, output_dir)
        results.append(r)

        if r["status"] == "success":
            success += 1
            print(f"  -> OK: {r['pages']} pages, {r['figures']} figures, "
                  f"{r['images_extracted']} images, sections: {r['sections_found']}")
        else:
            print(f"  -> FAILED: {r['error']}")

    report = {
        "summary": {"total": len(pdf_files), "success": success,
                     "failed": len(pdf_files) - success},
        "files": results,
        "config": {
            "tool": "pymupdf4llm",
            "timestamp": datetime.now().isoformat()
        }
    }

    report_path = output_dir / "conversion_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")

    print("-" * 50)
    print(f"Complete: {success}/{len(pdf_files)} converted")
    print(f"Report: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF to Markdown using pymupdf4llm"
    )
    parser.add_argument("--input-dir", "-i", type=Path, default=None,
                        help="Directory with PDF files")
    parser.add_argument("--single", "-s", type=Path, default=None,
                        help="Single PDF file")
    parser.add_argument("--output-dir", "-o", type=Path, required=True,
                        help="Output directory")

    args = parser.parse_args()

    if not args.input_dir and not args.single:
        parser.error("Either --input-dir or --single is required")

    if args.single:
        if not args.single.exists():
            print(f"Error: {args.single} not found")
            return 1
        r = convert_single_pdf(args.single, args.output_dir)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0 if r["status"] == "success" else 1
    else:
        if not args.input_dir.exists():
            print(f"Error: {args.input_dir} not found")
            return 1
        report = batch_convert(args.input_dir, args.output_dir)
        return 0 if report["summary"].get("failed", 0) == 0 else 1


if __name__ == "__main__":
    exit(main())
