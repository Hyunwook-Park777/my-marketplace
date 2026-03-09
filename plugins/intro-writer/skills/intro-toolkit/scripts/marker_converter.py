#!/usr/bin/env python3
"""
Marker PDF to Markdown Converter

PDF 논문을 Marker를 사용하여 Markdown으로 변환합니다.

Usage:
    python marker_converter.py --input-dir ./papers/ --output-dir ./converted/
    python marker_converter.py --single ./paper.pdf --output-dir ./converted/

Requirements:
    pip install marker-pdf
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def check_marker_installation() -> bool:
    """Marker 설치 확인"""
    try:
        result = subprocess.run(
            ["marker", "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def convert_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    language: str = "en"
) -> dict:
    """
    단일 PDF 파일을 Marker로 Markdown 변환

    Args:
        pdf_path: PDF 파일 경로
        output_dir: 출력 디렉토리
        language: OCR 언어

    Returns:
        변환 결과 딕셔너리
    """
    result = {
        "input": str(pdf_path),
        "output": None,
        "status": "pending",
        "pages": 0,
        "sections_found": [],
        "figures": 0,
        "tables": 0,
        "equations": 0,
        "warnings": [],
        "error": None
    }

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Marker CLI 실행
        cmd = [
            "marker_single",
            str(pdf_path),
            "--output_dir", str(output_dir),
            "--output_format", "markdown"
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if proc.returncode != 0:
            result["status"] = "failed"
            result["error"] = proc.stderr.strip() or f"marker_single exited with code {proc.returncode}"
            return result

        # Marker 출력 구조 처리: {out}/{stem}/{stem}.md → root로 flatten
        stem = pdf_path.stem
        nested_md = output_dir / stem / f"{stem}.md"
        flat_md = output_dir / f"{stem}.md"

        if nested_md.exists():
            shutil.move(str(nested_md), str(flat_md))
            # 이미지 폴더도 이동
            nested_images = output_dir / stem / "images"
            if nested_images.exists():
                flat_images = output_dir / "images"
                flat_images.mkdir(exist_ok=True)
                for img in nested_images.iterdir():
                    shutil.move(str(img), str(flat_images / img.name))
            # 빈 중첩 폴더 정리
            nested_dir = output_dir / stem
            if nested_dir.exists():
                shutil.rmtree(str(nested_dir), ignore_errors=True)

        if flat_md.exists():
            result["output"] = str(flat_md)
            result["status"] = "success"

            content = flat_md.read_text(encoding="utf-8")
            result["sections_found"] = extract_sections(content)
            result["figures"] = content.lower().count("figure")
            result["tables"] = content.count("|---")
            result["equations"] = content.count("$$") // 2 + content.count("$") // 2
            result["pages"] = max(1, len(content) // 3000)
        else:
            result["status"] = "failed"
            result["error"] = "Output file not created"

    except subprocess.TimeoutExpired:
        result["status"] = "failed"
        result["error"] = "Conversion timed out (300s)"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def extract_sections(content: str) -> list:
    """Markdown에서 섹션 헤더 추출"""
    import re

    sections = []
    section_patterns = [
        (r"#+\s*abstract", "Abstract"),
        (r"#+\s*introduction", "Introduction"),
        (r"#+\s*(materials?\s*(and|&)?\s*)?methods?", "Methods"),
        (r"#+\s*results?", "Results"),
        (r"#+\s*discussion", "Discussion"),
        (r"#+\s*conclusion", "Conclusion"),
        (r"#+\s*references?", "References"),
    ]

    content_lower = content.lower()

    for pattern, section_name in section_patterns:
        if re.search(pattern, content_lower):
            sections.append(section_name)

    return sections


def batch_convert(
    input_dir: Path,
    output_dir: Path,
    language: str = "en",
    workers: int = 4,
    min_papers: int = 3
) -> dict:
    """
    폴더 내 모든 PDF를 Marker로 일괄 변환

    Args:
        input_dir: PDF 파일들이 있는 디렉토리
        output_dir: 출력 디렉토리
        language: OCR 언어
        workers: 병렬 작업자 수
        min_papers: 최소 논문 수 (경고용)

    Returns:
        변환 리포트 딕셔너리
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_dir.glob("*.pdf"))

    if len(pdf_files) == 0:
        return {
            "error": f"No PDF files found in {input_dir}",
            "summary": {"total": 0}
        }

    if len(pdf_files) < min_papers:
        print(f"Warning: Found {len(pdf_files)} PDFs, recommended minimum is {min_papers}")

    print(f"Found {len(pdf_files)} PDF files")
    print(f"Output: {output_dir}")
    print("-" * 50)

    # Marker batch 명령어 시도
    cmd = [
        "marker",
        str(input_dir),
        "--output_dir", str(output_dir),
        "--workers", str(workers),
        "--output_format", "markdown"
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30분
        )

        if proc.returncode != 0:
            print(f"Batch conversion failed, falling back to single conversion...")
            return _fallback_single_convert(pdf_files, output_dir, language, min_papers)

    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Batch conversion unavailable, falling back to single conversion...")
        return _fallback_single_convert(pdf_files, output_dir, language, min_papers)

    # batch 후 결과 수집: flatten nested outputs
    results = []
    success_count = 0
    partial_count = 0
    failed_count = 0

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        nested_md = output_dir / stem / f"{stem}.md"
        flat_md = output_dir / f"{stem}.md"

        if nested_md.exists():
            shutil.move(str(nested_md), str(flat_md))
            nested_images = output_dir / stem / "images"
            if nested_images.exists():
                flat_images = output_dir / "images"
                flat_images.mkdir(exist_ok=True)
                for img in nested_images.iterdir():
                    shutil.move(str(img), str(flat_images / img.name))
            nested_dir = output_dir / stem
            if nested_dir.exists():
                shutil.rmtree(str(nested_dir), ignore_errors=True)

        if flat_md.exists():
            content = flat_md.read_text(encoding="utf-8")
            file_result = {
                "input": str(pdf_path),
                "output": str(flat_md),
                "status": "success",
                "pages": max(1, len(content) // 3000),
                "sections_found": extract_sections(content),
                "figures": content.lower().count("figure"),
                "tables": content.count("|---"),
                "equations": content.count("$$") // 2 + content.count("$") // 2
            }
            success_count += 1
        else:
            file_result = {
                "input": str(pdf_path),
                "output": None,
                "status": "failed",
                "error": "Output file not found after batch conversion"
            }
            failed_count += 1

        results.append(file_result)

    report = {
        "summary": {
            "total": len(pdf_files),
            "success": success_count,
            "partial": partial_count,
            "failed": failed_count
        },
        "files": results,
        "config": {
            "tool": "marker",
            "workers": workers,
            "language": language,
            "timestamp": datetime.now().isoformat()
        }
    }

    report_path = output_dir / "conversion_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("-" * 50)
    print(f"Conversion complete: {success_count} success, {partial_count} partial, {failed_count} failed")
    print(f"Report saved: {report_path}")

    return report


def _fallback_single_convert(
    pdf_files: list,
    output_dir: Path,
    language: str,
    min_papers: int
) -> dict:
    """batch 실패 시 개별 변환 폴백"""
    results = []
    success_count = 0
    partial_count = 0
    failed_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Converting: {pdf_path.name}")

        result = convert_single_pdf(pdf_path, output_dir, language)
        results.append(result)

        if result["status"] == "success":
            success_count += 1
            print(f"  -> Success: {len(result['sections_found'])} sections found")
        elif result["status"] == "partial":
            partial_count += 1
            print(f"  -> Partial: {result['warnings']}")
        else:
            failed_count += 1
            print(f"  -> Failed: {result['error']}")

    report = {
        "summary": {
            "total": len(pdf_files),
            "success": success_count,
            "partial": partial_count,
            "failed": failed_count
        },
        "files": results,
        "config": {
            "tool": "marker (single fallback)",
            "language": language,
            "timestamp": datetime.now().isoformat()
        }
    }

    report_path = output_dir / "conversion_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("-" * 50)
    print(f"Conversion complete: {success_count} success, {partial_count} partial, {failed_count} failed")
    print(f"Report saved: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF papers to Markdown using Marker"
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=Path,
        default=None,
        help="Directory containing PDF files (batch mode)"
    )
    parser.add_argument(
        "--single", "-s",
        type=Path,
        default=None,
        help="Single PDF file path"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        required=True,
        help="Output directory for converted Markdown files"
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        default="en",
        help="OCR language (default: en)"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=4,
        help="Number of parallel workers for batch mode (default: 4)"
    )
    parser.add_argument(
        "--min-papers",
        type=int,
        default=3,
        help="Minimum recommended papers (default: 3)"
    )

    args = parser.parse_args()

    if not args.input_dir and not args.single:
        parser.error("Either --input-dir or --single is required")

    if not check_marker_installation():
        print("Error: Marker is not installed.")
        print("Install with: pip install marker-pdf")
        sys.exit(1)

    if args.single:
        if not args.single.exists():
            print(f"Error: PDF file not found: {args.single}")
            sys.exit(1)
        result = convert_single_pdf(args.single, args.output_dir, args.language)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["status"] == "success" else 1)
    else:
        if not args.input_dir.exists():
            print(f"Error: Input directory not found: {args.input_dir}")
            sys.exit(1)
        report = batch_convert(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            language=args.language,
            workers=args.workers,
            min_papers=args.min_papers
        )
        if report.get("error"):
            sys.exit(1)
        elif report["summary"]["failed"] > 0:
            sys.exit(2)
        else:
            sys.exit(0)


if __name__ == "__main__":
    main()
