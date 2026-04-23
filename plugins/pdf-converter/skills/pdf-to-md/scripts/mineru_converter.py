#!/usr/bin/env python3
"""
MinerU PDF to Markdown Converter (General-purpose)

PDF 문서를 MinerU를 사용하여 Markdown으로 변환합니다.
학술 논문, 기술 문서, 보고서 등 모든 종류의 PDF를 지원합니다.

Usage:
    python mineru_converter.py --input-dir ./pdfs/ --output-dir ./converted/
    python mineru_converter.py --single ./document.pdf --output-dir ./converted/

Requirements:
    pip install "mineru[all]"
    pip install pymupdf  (optional, for accurate page count)
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional


# MinerU가 생성하는 불필요한 부가 파일 패턴
MINERU_JUNK_SUFFIXES = [
    "_content_list.json",
    "_layout.pdf",
    "_middle.json",
    "_model.json",
    "_origin.pdf",
    "_span.pdf",
]

# Windows MAX_PATH 제한
MAX_PATH_WINDOWS = 260
# MinerU 부가 파일 중 가장 긴 접미사
MINERU_LONGEST_SUFFIX = "_content_list.json"


def check_mineru_installation() -> bool:
    """MinerU 설치 확인"""
    try:
        result = subprocess.run(
            ["mineru", "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_pdf_page_count(pdf_path: Path) -> int:
    """PyMuPDF로 실제 PDF 페이지 수 추출. 미설치 시 추정치 반환."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except ImportError:
        # fitz 미설치 시 파일 크기 기반 추정
        size_kb = pdf_path.stat().st_size / 1024
        return max(1, int(size_kb / 50))
    except Exception:
        return 0


def estimate_max_path_length(output_dir: Path, stem: str) -> int:
    """
    MinerU가 생성할 최대 경로 길이를 추정.

    패턴: {output_dir}/{stem}/auto/{stem}{longest_suffix}
    """
    longest_path = output_dir / stem / "auto" / f"{stem}{MINERU_LONGEST_SUFFIX}"
    return len(str(longest_path))


def _get_short_temp_dir() -> Path:
    """Windows MAX_PATH 문제를 피하기 위한 짧은 임시 디렉토리 확보"""
    short_base = Path("C:/tmp/mc")
    try:
        short_base.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="mc_", dir=str(short_base)))
    except OSError:
        return Path(tempfile.mkdtemp(prefix="mc_"))


def flatten_mineru_output(output_dir: Path, stem: str) -> Optional[Path]:
    """
    MinerU 중첩 출력 구조를 평탄화

    MinerU 출력: {output_dir}/{stem}/auto/{stem}.md
    평탄화 결과: {output_dir}/{stem}.md + {output_dir}/{stem}/images/

    Returns:
        평탄화된 .md 파일 경로 또는 None
    """
    nested_md = output_dir / stem / "auto" / f"{stem}.md"
    flat_md = output_dir / f"{stem}.md"
    flat_md_result = None

    # MD 파일 이동 (존재할 때만)
    if nested_md.exists():
        shutil.move(str(nested_md), str(flat_md))
        flat_md_result = flat_md if flat_md.exists() else None

    # 이미지 폴더 이동: {stem}/auto/images/ → {stem}/images/ (문서별 폴더)
    nested_images = output_dir / stem / "auto" / "images"
    if nested_images.exists() and any(nested_images.iterdir()):
        paper_images = output_dir / stem / "images"
        paper_images.mkdir(parents=True, exist_ok=True)
        for img in nested_images.iterdir():
            if img.is_file():
                dest = paper_images / img.name
                if dest.exists():
                    dest.unlink()
                shutil.move(str(img), str(dest))

    # MD 내 이미지 참조 경로 업데이트: images/ → {stem}/images/
    if flat_md.exists():
        _update_image_references(flat_md, stem)

    # 불필요한 부가 파일 정리
    auto_dir = output_dir / stem / "auto"
    if auto_dir.exists():
        for suffix in MINERU_JUNK_SUFFIXES:
            junk = auto_dir / f"{stem}{suffix}"
            if junk.exists():
                junk.unlink()
        # auto/ 디렉토리만 정리 ({stem}/ 폴더는 이미지를 포함하므로 유지)
        shutil.rmtree(str(auto_dir), ignore_errors=True)

    return flat_md_result


def verify_image_references(md_path: Path, output_dir: Path) -> list:
    """
    MD 파일 내 이미지 참조가 실제 파일과 매칭되는지 검증.

    Returns:
        누락된 이미지 참조 목록
    """
    content = md_path.read_text(encoding="utf-8")
    image_refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', content)

    missing = []
    for ref in image_refs:
        if not ref.startswith(('http://', 'https://', '/')):
            # angle bracket 제거
            clean_ref = ref.strip('<>') if ref.startswith('<') and ref.endswith('>') else ref
            img_path = output_dir / clean_ref
            if not img_path.exists():
                missing.append(ref)

    return missing


def _update_image_references(md_path: Path, stem: str):
    """MD 파일 내 이미지 참조를 문서별 폴더 구조로 업데이트.

    MinerU 기본: images/xxx.jpg → 변환 후: {stem}/images/xxx.jpg
    """
    content = md_path.read_text(encoding="utf-8")
    prefix = f"]({stem}/images/"
    # 이미 업데이트된 경우 스킵
    if prefix in content:
        return
    updated = content.replace("](images/", prefix)
    if updated != content:
        md_path.write_text(updated, encoding="utf-8")


def extract_sections(content: str) -> list:
    """Markdown에서 모든 헤딩 추출 (범용)"""
    sections = []
    for match in re.finditer(r'^(#{1,3})\s+(.+)$', content, re.MULTILINE):
        level = len(match.group(1))
        title = match.group(2).strip()
        # 선행 점, 번호 제거하여 깔끔한 제목 추출
        clean_title = re.sub(r'^\.?\s*(\d+\.?\s*)?', '', title).strip()
        if clean_title:
            sections.append(clean_title)
    return sections


def convert_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    language: str = "en",
    backend: str = "pipeline",
    method: str = "auto",
    timeout: int = 3600
) -> dict:
    """
    단일 PDF 파일을 MinerU로 Markdown 변환

    Args:
        pdf_path: PDF 파일 경로
        output_dir: 출력 디렉토리
        language: OCR 언어
        backend: MinerU 백엔드 (pipeline, vlm-auto-engine 등)
        method: 파싱 방법 (auto, txt, ocr)
        timeout: 변환 타임아웃 (초, 기본 3600)

    Returns:
        변환 결과 딕셔너리
    """
    # 경로 길이 사전 검증 (Windows MAX_PATH)
    stem = pdf_path.stem
    estimated_len = estimate_max_path_length(output_dir, stem)
    if estimated_len >= MAX_PATH_WINDOWS:
        print(f"  Path too long ({estimated_len} chars), using short-path fallback...")
        return _convert_with_short_path(
            pdf_path, output_dir, language, backend, method, timeout
        )

    result = {
        "input": str(pdf_path),
        "output": None,
        "status": "pending",
        "pages": get_pdf_page_count(pdf_path),
        "sections_found": [],
        "figures": 0,
        "tables": 0,
        "equations": 0,
        "warnings": [],
        "error": None
    }

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        # MinerU CLI 실행
        cmd = [
            "mineru",
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "-b", backend,
            "-l", language,
            "-m", method
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if proc.returncode != 0:
            result["status"] = "failed"
            result["error"] = proc.stderr.strip() or f"mineru exited with code {proc.returncode}"
            return result

        # MinerU 출력 구조 처리: {out}/{stem}/auto/{stem}.md → root로 flatten
        flat_md = flatten_mineru_output(output_dir, stem)

        if flat_md and flat_md.exists():
            result["output"] = str(flat_md)
            result["status"] = "success"

            content = flat_md.read_text(encoding="utf-8")
            result["sections_found"] = extract_sections(content)
            result["figures"] = len(re.findall(r'!\[', content))
            result["tables"] = content.lower().count("<table")
            result["equations"] = content.count("$$") // 2 + content.count("$") // 2

            # 이미지 참조 검증
            missing = verify_image_references(flat_md, output_dir)
            if missing:
                result["warnings"].append(
                    f"Missing {len(missing)} image(s): {', '.join(missing[:3])}"
                )
        else:
            result["status"] = "failed"
            result["error"] = "Output file not created"

    except subprocess.TimeoutExpired:
        result["status"] = "failed"
        result["error"] = f"Conversion timed out ({timeout}s)"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def _convert_with_short_path(
    pdf_path: Path,
    final_output_dir: Path,
    language: str = "en",
    backend: str = "pipeline",
    method: str = "auto",
    timeout: int = 3600
) -> dict:
    """
    경로가 긴 PDF를 짧은 임시 디렉토리에서 변환 후 결과를 최종 위치로 이동.

    Windows MAX_PATH (260자) 제한 우회용.
    """
    result = {
        "input": str(pdf_path),
        "output": None,
        "status": "pending",
        "pages": get_pdf_page_count(pdf_path),
        "sections_found": [],
        "figures": 0,
        "tables": 0,
        "equations": 0,
        "warnings": ["Used short-path fallback due to Windows MAX_PATH limit"],
        "error": None
    }

    tmp_dir = None
    try:
        # 짧은 임시 디렉토리 생성
        tmp_dir = _get_short_temp_dir()
        short_stem = hashlib.md5(pdf_path.stem.encode()).hexdigest()[:8]
        tmp_pdf = tmp_dir / f"{short_stem}.pdf"
        shutil.copy2(str(pdf_path), str(tmp_pdf))

        # 임시 dir의 하위 출력 폴더
        tmp_out = tmp_dir / "out"
        tmp_out.mkdir()

        # MinerU CLI 실행
        cmd = [
            "mineru",
            "-p", str(tmp_pdf),
            "-o", str(tmp_out),
            "-b", backend,
            "-l", language,
            "-m", method
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if proc.returncode != 0:
            result["status"] = "failed"
            result["error"] = proc.stderr.strip() or f"mineru exited with code {proc.returncode}"
            return result

        # 평탄화 (임시 dir 내에서)
        flat_md = flatten_mineru_output(tmp_out, short_stem)

        if not flat_md or not flat_md.exists():
            result["status"] = "failed"
            result["error"] = "Output file not created in temp directory"
            return result

        # 결과를 최종 위치로 이동 (원래 stem 이름 복원)
        original_stem = pdf_path.stem
        final_output_dir.mkdir(parents=True, exist_ok=True)

        # MD 파일 이동 + 이름 복원
        final_md = final_output_dir / f"{original_stem}.md"
        shutil.move(str(flat_md), str(final_md))

        # 이미지 이동 (문서별 폴더)
        tmp_images = tmp_out / short_stem / "images"
        if tmp_images.exists() and any(tmp_images.iterdir()):
            final_images = final_output_dir / original_stem / "images"
            final_images.mkdir(parents=True, exist_ok=True)
            for img in tmp_images.iterdir():
                if img.is_file():
                    dest = final_images / img.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(img), str(dest))

        # 이미지 참조: short_stem → original_stem 교체
        if final_md.exists():
            _content = final_md.read_text(encoding="utf-8")
            _updated = _content.replace(
                f"]({short_stem}/images/",
                f"]({original_stem}/images/"
            )
            if _updated != _content:
                final_md.write_text(_updated, encoding="utf-8")

        # 통계 수집
        content = final_md.read_text(encoding="utf-8")
        result["output"] = str(final_md)
        result["status"] = "success"
        result["sections_found"] = extract_sections(content)
        result["figures"] = len(re.findall(r'!\[', content))
        result["tables"] = content.lower().count("<table")
        result["equations"] = content.count("$$") // 2 + content.count("$") // 2

        # 이미지 참조 검증
        missing = verify_image_references(final_md, final_output_dir)
        if missing:
            result["warnings"].append(
                f"Missing {len(missing)} image(s): {', '.join(missing[:3])}"
            )

    except subprocess.TimeoutExpired:
        result["status"] = "failed"
        result["error"] = f"Conversion timed out ({timeout}s)"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    return result


def batch_convert(
    input_dir: Path,
    output_dir: Path,
    language: str = "en",
    backend: str = "pipeline",
    method: str = "auto",
    timeout: int = 3600
) -> dict:
    """
    폴더 내 모든 PDF를 MinerU로 일괄 변환

    MinerU CLI는 디렉토리를 입력으로 받아 자체 배치 처리 수행.
    변환 후 각 PDF의 중첩 출력을 평탄화하여 정리.
    배치 후 실패 파일은 짧은 경로 폴백으로 자동 재시도.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_dir.glob("*.pdf"))

    if len(pdf_files) == 0:
        return {
            "error": f"No PDF files found in {input_dir}",
            "summary": {"total": 0}
        }

    print(f"Found {len(pdf_files)} PDF files")
    print(f"Output: {output_dir}")
    print(f"Backend: {backend}, Language: {language}, Method: {method}")
    print("-" * 50)

    # MinerU CLI 배치 실행 (디렉토리 입력)
    batch_timeout = timeout * len(pdf_files)
    cmd = [
        "mineru",
        "-p", str(input_dir),
        "-o", str(output_dir),
        "-b", backend,
        "-l", language,
        "-m", method
    ]

    batch_success = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=batch_timeout
        )
        batch_success = (proc.returncode == 0)
        if not batch_success:
            print(f"Batch conversion failed (exit code {proc.returncode})")
            print(f"stderr: {proc.stderr[:500] if proc.stderr else 'none'}")
    except subprocess.TimeoutExpired:
        print("Batch conversion timed out")
    except FileNotFoundError:
        print("mineru command not found")

    # 배치 실패 시 개별 변환 폴백
    if not batch_success:
        print("Falling back to single file conversion...")
        return _fallback_single_convert(
            pdf_files, output_dir, language, backend, method, timeout
        )

    # 배치 성공 시 결과 수집 및 flatten
    results = []
    success_count = 0
    failed_pdfs = []

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        flat_md = flatten_mineru_output(output_dir, stem)

        if flat_md and flat_md.exists():
            content = flat_md.read_text(encoding="utf-8")
            file_result = {
                "input": str(pdf_path),
                "output": str(flat_md),
                "status": "success",
                "pages": get_pdf_page_count(pdf_path),
                "sections_found": extract_sections(content),
                "figures": len(re.findall(r'!\[', content)),
                "tables": content.lower().count("<table"),
                "equations": content.count("$$") // 2 + content.count("$") // 2
            }
            results.append(file_result)
            success_count += 1
            print(f"  [{success_count + len(failed_pdfs)}/{len(pdf_files)}] {stem}: OK")
        else:
            failed_pdfs.append(pdf_path)
            print(f"  [{success_count + len(failed_pdfs)}/{len(pdf_files)}] {stem}: FAILED (will retry)")

    # 실패 파일 짧은 경로 폴백 재시도
    if failed_pdfs:
        print(f"\nRetrying {len(failed_pdfs)} failed file(s) with short-path fallback...")
        for pdf_path in failed_pdfs:
            print(f"  Retrying: {pdf_path.name}")
            retry_result = _convert_with_short_path(
                pdf_path, output_dir, language, backend, method, timeout
            )
            results.append(retry_result)
            if retry_result["status"] == "success":
                success_count += 1
                print(f"    -> Retry SUCCESS")
            else:
                print(f"    -> Retry FAILED: {retry_result.get('error', 'Unknown')}")

    failed_count = len(pdf_files) - success_count
    report = _build_report(results, pdf_files, success_count, failed_count,
                           output_dir, backend, language, method)
    return report


def _fallback_single_convert(
    pdf_files: list,
    output_dir: Path,
    language: str,
    backend: str,
    method: str,
    timeout: int
) -> dict:
    """배치 실패 시 개별 변환 폴백"""
    results = []
    success_count = 0
    failed_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Converting: {pdf_path.name}")

        result = convert_single_pdf(pdf_path, output_dir, language, backend, method, timeout)
        results.append(result)

        if result["status"] == "success":
            success_count += 1
            print(f"  -> Success: {len(result['sections_found'])} sections found")
        else:
            failed_count += 1
            print(f"  -> Failed: {result['error']}")

    report = _build_report(results, pdf_files, success_count, failed_count,
                           output_dir, backend, language, method)
    return report


def _build_report(
    results: list,
    pdf_files: list,
    success_count: int,
    failed_count: int,
    output_dir: Path,
    backend: str,
    language: str,
    method: str
) -> dict:
    """변환 리포트 생성 및 저장"""
    report = {
        "summary": {
            "total": len(pdf_files),
            "success": success_count,
            "failed": failed_count
        },
        "files": results,
        "config": {
            "tool": "mineru",
            "backend": backend,
            "language": language,
            "method": method,
            "timestamp": datetime.now().isoformat()
        }
    }

    report_path = output_dir / "conversion_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("-" * 50)
    print(f"Conversion complete: {success_count} success, {failed_count} failed")
    print(f"Report saved: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF documents to Markdown using MinerU"
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
        "--backend", "-b",
        type=str,
        default="pipeline",
        choices=["pipeline", "vlm-auto-engine", "hybrid-auto-engine",
                 "vlm-http-client", "hybrid-http-client"],
        help="MinerU backend (default: pipeline)"
    )
    parser.add_argument(
        "--method", "-m",
        type=str,
        default="auto",
        choices=["auto", "txt", "ocr"],
        help="Parsing method (default: auto)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=3600,
        help="Conversion timeout in seconds (default: 3600)"
    )

    args = parser.parse_args()

    if not args.input_dir and not args.single:
        parser.error("Either --input-dir or --single is required")

    if not check_mineru_installation():
        print("Error: MinerU is not installed.")
        print('Install with: pip install "mineru[all]"')
        sys.exit(1)

    if args.single:
        if not args.single.exists():
            print(f"Error: PDF file not found: {args.single}")
            sys.exit(1)
        result = convert_single_pdf(
            args.single, args.output_dir, args.language,
            args.backend, args.method, args.timeout
        )
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
            backend=args.backend,
            method=args.method,
            timeout=args.timeout
        )
        if report.get("error"):
            sys.exit(1)
        elif report["summary"]["failed"] > 0:
            sys.exit(2)
        else:
            sys.exit(0)


if __name__ == "__main__":
    main()
