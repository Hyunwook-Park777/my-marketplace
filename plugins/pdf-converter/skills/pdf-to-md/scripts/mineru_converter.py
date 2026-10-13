#!/usr/bin/env python3
"""
MinerU PDF to Markdown Converter (General-purpose)

PDF 문서를 MinerU를 사용하여 Markdown으로 변환합니다.
학술 논문, 기술 문서, 보고서 등 모든 종류의 PDF를 지원합니다.

Usage:
    python mineru_converter.py --input-dir ./pdfs/ --output-dir ./converted/
    python mineru_converter.py --single ./document.pdf --output-dir ./converted/

Requirements:
    pip install "mineru[all]<3"          (MinerU 2.x, base Python)
    MinerU 4.x: separate venv, see SKILL.md (optional; used by --engine auto/mineru4)
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
# MinerU 파싱 하위 폴더 중 가장 긴 이름 (auto / txt / ocr / vlm / hybrid_auto ...)
MINERU_LONGEST_SUBDIR = "hybrid_auto"

# MinerU `-l` 은 ISO 코드(ko/ja/zh)가 아닌 자체 이름(korean/japan/ch)만 허용한다.
# 사용자가 흔히 쓰는 ISO 코드를 MinerU 이름으로 변환한다.
LANG_ALIASES = {
    "ko": "korean", "kr": "korean", "kor": "korean",
    "ja": "japan", "jp": "japan", "jpn": "japan", "japanese": "japan",
    "zh": "ch", "zh-cn": "ch", "zh_cn": "ch", "cn": "ch", "chinese": "ch",
    "zh-tw": "chinese_cht", "zh_tw": "chinese_cht", "tw": "chinese_cht",
    "eng": "en", "english": "en",
    "ru": "east_slavic", "uk": "east_slavic",
    "ar": "arabic", "hi": "devanagari",
}


def normalize_language(language: str) -> str:
    """ISO 언어 코드를 MinerU `-l` 값으로 변환 (모르는 값은 그대로 전달)"""
    key = language.strip().lower()
    return LANG_ALIASES.get(key, key)


def get_mineru_cmd() -> list:
    """MinerU CLI 커맨드 반환.

    Windows Device Guard / Application Control 로 `mineru.exe`, `mineru` shim 이
    차단된 환경에서도 동작하도록, 항상 `python -m mineru.cli.client` 형태로 호출한다.
    이 방식은 설치된 Python 인터프리터만 있으면 플랫폼/정책에 관계없이 동작한다.
    """
    return [sys.executable, "-m", "mineru.cli.client"]


def detect_cuda_device() -> Optional[str]:
    """PyTorch CUDA 가용 여부 감지.

    Returns:
        "cuda" if GPU usable, else None (CPU 사용)
    """
    try:
        import torch
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return None


def mineru_error_hint(stderr: str) -> str:
    """MinerU stderr 에서 마지막 ERROR/Exception 줄을 뽑는다.

    MinerU 는 모델 로드 실패(예: lmdeploy 버전 불일치) 시에도 종료 코드 0 을 반환하므로
    '결과 파일 없음' 만으로는 원인을 알 수 없다.
    """
    lines = [re.sub(r'\x1b\[[0-9;]*m', '', l).strip() for l in (stderr or "").splitlines()]
    hits = [l for l in lines if re.search(r'\b(ERROR|Error|Exception)\b', l)]
    return hits[-1][-300:] if hits else ""


def check_mineru_installation() -> bool:
    """MinerU 설치 확인 (Device Guard 안전)"""
    try:
        result = subprocess.run(
            get_mineru_cmd() + ["--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_pdf_page_count(pdf_path: Path) -> int:
    """PyMuPDF로 실제 PDF 페이지 수 추출. 미설치 시 추정치 반환.

    Device Guard 로 `fitz` shim DLL 이 차단된 환경에서는 `pymupdf` 직접 임포트로 폴백.
    """
    try:
        try:
            import pymupdf as _fitz
        except ImportError:
            import fitz as _fitz  # type: ignore
        doc = _fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except ImportError:
        size_kb = pdf_path.stat().st_size / 1024
        return max(1, int(size_kb / 50))
    except Exception:
        return 0


def estimate_max_path_length(output_dir: Path, stem: str) -> int:
    """
    MinerU가 생성할 최대 경로 길이를 추정.

    패턴: {output_dir}/{stem}/{parse_subdir}/{stem}{longest_suffix}
    """
    # 이미지 파일명은 sha256(64자) + 확장자라 stem 이 짧으면 이미지 경로가 더 길다
    tail = max(len(stem) + len(MINERU_LONGEST_SUFFIX), len("images/") + 64 + len(".jpeg"))
    return len(str(output_dir.resolve() / stem / MINERU_LONGEST_SUBDIR)) + 1 + tail


def find_mineru_parse_dir(output_dir: Path, stem: str) -> Optional[Path]:
    """MinerU 가 {stem}.md 를 쓴 하위 폴더를 찾는다.

    하위 폴더 이름은 백엔드/메서드에 따라 다르다:
    pipeline → auto|txt|ocr, vlm-* → vlm, hybrid-* → hybrid_auto|hybrid_txt|hybrid_ocr
    """
    stem_dir = output_dir / stem
    if not stem_dir.is_dir():
        return None
    candidates = [d for d in stem_dir.iterdir()
                  if d.is_dir() and (d / f"{stem}.md").exists()]
    if not candidates:
        return None
    # 같은 출력 폴더에 여러 번 변환한 경우 가장 최근 결과를 사용
    return max(candidates, key=lambda d: (d / f"{stem}.md").stat().st_mtime)


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

    MinerU 출력: {output_dir}/{stem}/{auto|ocr|txt|vlm|hybrid_auto|...}/{stem}.md
    평탄화 결과: {output_dir}/{stem}.md + {output_dir}/{stem}/images/

    Returns:
        평탄화된 .md 파일 경로 또는 None
    """
    parse_dir = find_mineru_parse_dir(output_dir, stem)
    flat_md = output_dir / f"{stem}.md"
    if parse_dir is None:
        return None

    # MD 파일 이동
    nested_md = parse_dir / f"{stem}.md"
    shutil.move(str(nested_md), str(flat_md))
    flat_md_result = flat_md if flat_md.exists() else None

    # 이미지 폴더 이동: {stem}/{parse_dir}/images/ → {stem}/images/ (문서별 폴더)
    nested_images = parse_dir / "images"
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

    # 불필요한 부가 파일 정리: 파싱 하위 폴더만 삭제 ({stem}/ 폴더는 이미지를 포함하므로 유지)
    shutil.rmtree(str(parse_dir), ignore_errors=True)

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
    timeout: int = 3600,
    device: Optional[str] = None
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
        device: 추론 디바이스 ("cuda"/"cpu"/None). None이면 자동 감지.

    Returns:
        변환 결과 딕셔너리
    """
    # 경로 길이 사전 검증 (Windows MAX_PATH)
    stem = pdf_path.stem
    estimated_len = estimate_max_path_length(output_dir, stem)
    if estimated_len >= MAX_PATH_WINDOWS:
        print(f"  Path too long ({estimated_len} chars), using short-path fallback...")
        return _convert_with_short_path(
            pdf_path, output_dir, language, backend, method, timeout, device
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

        # MinerU CLI 실행 (Device Guard 안전 + GPU 자동)
        resolved_device = device if device is not None else (detect_cuda_device() or "cpu")
        cmd = get_mineru_cmd() + [
            "-p", str(pdf_path),
            "-o", str(output_dir),
            "-b", backend,
            "-l", language,
            "-m", method,
            "-d", resolved_device
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
            hint = mineru_error_hint(proc.stderr)
            result["error"] = "Output file not created" + (f" (MinerU: {hint})" if hint else "")

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
    timeout: int = 3600,
    device: Optional[str] = None
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

        # MinerU CLI 실행 (Device Guard 안전 + GPU 자동)
        resolved_device = device if device is not None else (detect_cuda_device() or "cpu")
        cmd = get_mineru_cmd() + [
            "-p", str(tmp_pdf),
            "-o", str(tmp_out),
            "-b", backend,
            "-l", language,
            "-m", method,
            "-d", resolved_device
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
            hint = mineru_error_hint(proc.stderr)
            result["error"] = "Output file not created in temp directory" + (f" (MinerU: {hint})" if hint else "")
            return result

        # 결과를 최종 위치로 이동 (원래 stem 이름 복원)
        original_stem = pdf_path.stem
        final_output_dir.mkdir(parents=True, exist_ok=True)

        # MD 파일 이동 + 이름 복원
        final_md = final_output_dir / f"{original_stem}.md"
        shutil.move(str(flat_md), str(final_md))

        # 앞선 배치 시도가 긴 경로에 남긴 미완성 파싱 폴더 정리 ({stem}/auto 등, images 는 유지)
        final_stem_dir = final_output_dir / original_stem
        if final_stem_dir.is_dir():
            for sub in final_stem_dir.iterdir():
                if sub.is_dir() and sub.name != "images":
                    shutil.rmtree(str(sub), ignore_errors=True)

        # 이미지 이동 (문서별 폴더). 최종 경로도 MAX_PATH 를 넘으면 sha256 파일명을
        # img_001.jpg 처럼 짧게 바꾼다. 그대로 옮기면 WinError 3 으로 이미지가 사라진다.
        _content = final_md.read_text(encoding="utf-8")
        tmp_images = tmp_out / short_stem / "images"
        final_images = final_stem_dir / "images"
        if tmp_images.exists() and any(tmp_images.iterdir()):
            final_images.mkdir(parents=True, exist_ok=True)
            imgs = sorted(p for p in tmp_images.iterdir() if p.is_file())
            longest = max(len(str(final_images.resolve() / p.name)) for p in imgs)
            rename = longest >= MAX_PATH_WINDOWS
            if rename:
                result["warnings"].append("Image files renamed to img_NNN to fit Windows MAX_PATH")
            for n, img in enumerate(imgs, 1):
                new_name = f"img_{n:03d}{img.suffix}" if rename else img.name
                dest = final_images / new_name
                if dest.exists():
                    dest.unlink()
                shutil.move(str(img), str(dest))
                if rename:
                    _content = _content.replace(f"{short_stem}/images/{img.name}",
                                                f"{short_stem}/images/{new_name}")

        # 이미지 참조: short_stem → original_stem 교체
        _content = _content.replace(f"]({short_stem}/images/", f"]({original_stem}/images/")
        final_md.write_text(_content, encoding="utf-8")

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
    timeout: int = 3600,
    device: Optional[str] = None
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

    resolved_device = device if device is not None else (detect_cuda_device() or "cpu")

    print(f"Found {len(pdf_files)} PDF files")
    print(f"Output: {output_dir}")
    print(f"Backend: {backend}, Language: {language}, Method: {method}, Device: {resolved_device}")
    print("-" * 50)

    # MinerU CLI 배치 실행 (디렉토리 입력, Device Guard 안전)
    batch_timeout = timeout * len(pdf_files)
    cmd = get_mineru_cmd() + [
        "-p", str(input_dir),
        "-o", str(output_dir),
        "-b", backend,
        "-l", language,
        "-m", method,
        "-d", resolved_device
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
        hint = mineru_error_hint(proc.stderr)
        if hint:
            print(f"MinerU reported: {hint}")
        if not batch_success:
            print(f"Batch conversion failed (exit code {proc.returncode})")
            print(f"stderr: {proc.stderr[:500] if proc.stderr else 'none'}")
    except subprocess.TimeoutExpired:
        print("Batch conversion timed out")
    except FileNotFoundError:
        print("MinerU not found (checked: python -m mineru.cli.client)")

    # 배치 실패 시 개별 변환 폴백
    if not batch_success:
        print("Falling back to single file conversion...")
        return _fallback_single_convert(
            pdf_files, output_dir, language, backend, method, timeout, resolved_device
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
                pdf_path, output_dir, language, backend, method, timeout, resolved_device
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
    timeout: int,
    device: Optional[str] = None
) -> dict:
    """배치 실패 시 개별 변환 폴백"""
    results = []
    success_count = 0
    failed_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Converting: {pdf_path.name}")

        result = convert_single_pdf(pdf_path, output_dir, language, backend, method, timeout, device)
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


def detect_pdf_language(pdf_path: Path) -> Optional[str]:
    """PDF 텍스트 층으로 언어 추정: 한글 비율이 높으면 'korean', 라틴 문자면 'en', 텍스트가 없으면(스캔) None"""
    try:
        try:
            import pymupdf as _fitz
        except ImportError:
            import fitz as _fitz  # type: ignore
        doc = _fitz.open(str(pdf_path))
        # 앞쪽은 표지/이미지 페이지인 경우가 많아 문서 전체에서 고르게 최대 15쪽을 본다
        n = len(doc)
        idx = sorted({int(i * n / 15) for i in range(15)}) if n > 15 else range(n)
        pages = [doc[i] for i in idx]
        text = "".join(p.get_text() for p in pages)
        doc.close()
    except Exception:
        return None
    hangul = len(re.findall(r"[\uac00-\ud7a3]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul + latin < 50 * max(1, len(pages)):
        return None
    return "korean" if hangul > latin * 0.2 else "en"


def main():
    from mineru4_converter import (
        DEFAULT_TIER, MINERU4_TIERS, convert_with_mineru4, find_mineru4_python, probe_mineru4,
    )
    # Windows 파이프 기본 인코딩(cp949)에서는 일부 문자 출력 시 UnicodeEncodeError 로 종료된다
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
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
        default=None,
        help="MinerU 2.x OCR language: en, korean, japan, ch, ... (ISO codes ko/ja/zh are mapped). "
             "Default: detected per PDF (Hangul text -> korean, else en)"
    )
    parser.add_argument(
        "--backend", "-b",
        type=str,
        default="pipeline",
        choices=["pipeline", "vlm-auto-engine", "hybrid-auto-engine",
                 "vlm-http-client", "hybrid-http-client"],
        help="MinerU backend (default: pipeline, GPU via -d cuda). hybrid/vlm on Windows need lmdeploy matching this MinerU version"
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
    parser.add_argument(
        "--device", "-d",
        type=str,
        default=None,
        help="Inference device: 'cuda', 'cpu', 'cuda:0', etc. If omitted, uses CUDA (fails if unavailable unless --allow-cpu)."
    )
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="Fall back to CPU when CUDA is unavailable (default: stop with an error, GPU only)"
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "mineru2", "mineru4"],
        default="auto",
        help="auto: Korean/scanned-Korean PDFs -> MinerU 2.x (korean OCR), others -> MinerU 4.x; "
             "falls back to mineru2 when no MinerU 4 venv is found (default: auto)"
    )
    parser.add_argument(
        "--tier",
        choices=MINERU4_TIERS,
        default=DEFAULT_TIER,
        help="MinerU 4.x quality tier (default: advanced)"
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="MinerU 4.x page selection, e.g. '1-5,8' or 'r3-r1' (default: all pages)"
    )
    parser.add_argument(
        "--mineru4-python",
        default=None,
        help="python.exe of the MinerU 4.x venv (default: $MINERU4_PYTHON, then ~/venvs/mineru4)"
    )

    args = parser.parse_args()

    if not args.input_dir and not args.single:
        parser.error("Either --input-dir or --single is required")

    if args.single:
        if not args.single.exists():
            print(f"Error: PDF file not found: {args.single}")
            sys.exit(1)
        pdfs = [args.single]
    else:
        if not args.input_dir.exists():
            print(f"Error: Input directory not found: {args.input_dir}")
            sys.exit(1)
        pdfs = sorted(args.input_dir.glob("*.pdf"))
        if not pdfs:
            print(f"Error: No PDF files found in {args.input_dir}")
            sys.exit(1)

    # MinerU 4.x 사용 가능 여부 (auto 는 없으면 2.x 로 대체)
    m4_python = None
    if args.engine in ("auto", "mineru4"):
        m4_python = find_mineru4_python(args.mineru4_python)
        info = probe_mineru4(m4_python) if m4_python else {"ok": False, "error": "MinerU 4 venv not found"}
        problem = None
        if not info.get("ok"):
            problem = f"MinerU 4.x unavailable ({info.get('error') or info.get('version')})"
        elif not info.get("cuda") and not args.allow_cpu:
            problem = "MinerU 4.x venv has no CUDA PyTorch (GPU only; pass --allow-cpu to override)"
        if problem:
            if args.engine == "mineru4":
                print(f"Error: {problem}", file=sys.stderr)
                sys.exit(3 if "CUDA" in problem else 1)
            print(f"Warning: {problem} -> using MinerU 2.x for all files", file=sys.stderr)
            m4_python = None

    # 파일별 엔진/언어 결정
    user_lang = normalize_language(args.language) if args.language else None
    plan = {}
    for pdf in pdfs:
        lang = user_lang or detect_pdf_language(pdf) or "en"
        if args.engine == "mineru2" or m4_python is None:
            engine = "mineru2"
        elif args.engine == "mineru4":
            engine = "mineru4"
        else:
            # MinerU 4.x 는 이미지/스캔 영역 한글 OCR 이 불안정해 한국어는 2.x korean OCR 로 보낸다
            engine = "mineru2" if lang == "korean" else "mineru4"
        plan[pdf] = (engine, lang)
        print(f"  plan: {pdf.name} -> {engine} ({lang})", file=sys.stderr)

    results = []
    m2_files = [p for p in pdfs if plan[p][0] == "mineru2"]
    if m2_files:
        # GPU 전용 정책: CPU 변환은 수백 페이지 문서에서 수십 배 느리므로 조용히 폴백하지 않는다
        if args.device is None:
            args.device = detect_cuda_device()
            if args.device is None:
                if not args.allow_cpu:
                    print("Error: CUDA GPU not available (torch.cuda.is_available() is False).", file=sys.stderr)
                    print("Install CUDA PyTorch, or pass --allow-cpu / --device cpu to run on CPU.", file=sys.stderr)
                    sys.exit(3)
                args.device = "cpu"
        if not check_mineru_installation():
            print("Error: MinerU 2.x is not installed or cannot be launched.", file=sys.stderr)
            print('Install: pip install "mineru[all]<3"', file=sys.stderr)
            print("This script invokes MinerU 2.x via 'python -m mineru.cli.client' to avoid "
                  "Device Guard / Application Control blocks on mineru.exe.", file=sys.stderr)
            sys.exit(1)
        for lang in sorted({plan[p][1] for p in m2_files}):
            group = [p for p in m2_files if plan[p][1] == lang]
            if args.single:
                group_results = [convert_single_pdf(
                    args.single, args.output_dir, lang, args.backend, args.method, args.timeout, args.device)]
            elif len(group) == len(pdfs):
                group_results = batch_convert(args.input_dir, args.output_dir, lang, args.backend,
                                              args.method, args.timeout, args.device).get("files", [])
            else:
                # 폴더 일부만 이 엔진/언어로 갈 때도 모델을 한 번만 로드하도록 임시 폴더에 모아 배치 변환
                group_dir = _get_short_temp_dir()
                try:
                    for p in group:
                        shutil.copy2(str(p), str(group_dir / p.name))
                    group_results = batch_convert(group_dir, args.output_dir, lang, args.backend,
                                                  args.method, args.timeout, args.device).get("files", [])
                finally:
                    shutil.rmtree(str(group_dir), ignore_errors=True)
                originals = {p.name: str(p) for p in group}
                for r in group_results:
                    r["input"] = originals.get(Path(r["input"]).name, r["input"])
            for r in group_results:
                r.setdefault("engine", f"mineru2:{args.backend}:{lang}")
            results += group_results

    m4_files = [p for p in pdfs if plan[p][0] == "mineru4"]
    if m4_files:
        results += convert_with_mineru4(m4_files, args.output_dir, m4_python, args.tier,
                                        args.method, args.pages, args.timeout)

    if args.single:
        print(json.dumps(results[0], indent=2, ensure_ascii=False))
        sys.exit(0 if results[0]["status"] == "success" else 1)

    success = sum(1 for r in results if r.get("status") == "success")
    _build_report(results, pdfs, success, len(pdfs) - success, args.output_dir,
                           args.backend, user_lang or "auto", args.method)
    sys.exit(0 if success == len(pdfs) else 2)


if __name__ == "__main__":
    main()
