#!/usr/bin/env python3
"""
Figure Verification & Repair for Converted Markdown Files

변환된 MD 파일에서 이미지 참조(![])가 정상적으로 포함되어 있는지 검증하고,
누락된 파일을 자동으로 MinerU 재변환하여 복구합니다.

Usage:
    # 검증만 수행
    python verify_figures.py --md-dir ./md_converted/ --mode verify

    # 검증 + 자동 복구 (PDF 폴더 필요)
    python verify_figures.py --md-dir ./md_converted/ --pdf-dir ./pdfs/ --mode repair

    # 이미지 폴더 존재 여부도 함께 검증
    python verify_figures.py --md-dir ./md_converted/ --mode verify --check-images

Features:
    - MD 파일별 이미지 참조 수 카운트
    - 이미지 참조 0개인 파일 감지 (figure-missing)
    - 이미지 폴더/파일 실존 검증 (--check-images)
    - 자동 복구: MinerU 재변환 + postprocessor 적용
    - JSON 리포트 출력
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def count_image_refs(content: str) -> int:
    """MD 콘텐츠에서 이미지 참조 수를 카운트"""
    return len(re.findall(r'!\[', content))


def check_image_files_exist(md_path: Path, content: str, md_dir: Path) -> dict:
    """이미지 참조가 실제 파일로 존재하는지 검증

    CommonMark angle bracket 경로도 지원: ![](<path with spaces>)
    """
    image_refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', content)
    existing = 0
    missing = []

    for ref in image_refs:
        # angle bracket 제거: <path with spaces> → path with spaces
        clean_ref = ref.strip('<>') if ref.startswith('<') and ref.endswith('>') else ref
        # 상대 경로 해석
        img_path = md_dir / clean_ref
        if img_path.exists():
            existing += 1
        else:
            missing.append(clean_ref)

    return {
        "total_refs": len(image_refs),
        "existing": existing,
        "missing_count": len(missing),
        "missing_files": missing[:10]  # 최대 10개만 리포트
    }


def verify_md_dir(md_dir: Path, check_images: bool = False) -> dict:
    """MD 디렉토리 전체 검증"""
    md_files = sorted(md_dir.glob("*.md"))
    md_files = [f for f in md_files if f.name != "conversion_report.json"]

    results = {
        "total_files": len(md_files),
        "files_with_figures": 0,
        "files_without_figures": 0,
        "total_image_refs": 0,
        "files": [],
        "missing_figures": []
    }

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        img_count = count_image_refs(content)

        file_result = {
            "file": md_path.name,
            "image_refs": img_count,
            "status": "ok" if img_count > 0 else "no_figures"
        }

        if check_images and img_count > 0:
            img_check = check_image_files_exist(md_path, content, md_dir)
            file_result["image_files"] = img_check
            if img_check["missing_count"] > 0:
                file_result["status"] = "broken_refs"

        results["files"].append(file_result)
        results["total_image_refs"] += img_count

        if img_count > 0:
            results["files_with_figures"] += 1
        else:
            results["files_without_figures"] += 1
            results["missing_figures"].append(md_path.name)

    return results


def find_matching_pdf(md_name: str, pdf_dir: Path) -> Path | None:
    """MD 파일명으로 대응하는 PDF를 찾기"""
    stem = Path(md_name).stem

    # 정확히 일치
    exact = pdf_dir / f"{stem}.pdf"
    if exact.exists():
        return exact

    # 대소문자 무시 매칭
    for pdf in pdf_dir.glob("*.pdf"):
        if pdf.stem.lower() == stem.lower():
            return pdf

    # 부분 매칭 (긴 이름이 잘린 경우)
    for pdf in pdf_dir.glob("*.pdf"):
        if stem in pdf.stem or pdf.stem in stem:
            return pdf

    return None


def repair_missing_figures(
    md_dir: Path,
    pdf_dir: Path,
    verify_result: dict,
    script_dir: Path
) -> dict:
    """이미지 누락 파일을 MinerU 재변환으로 복구"""
    converter_script = script_dir / "mineru_converter.py"
    postprocessor_script = script_dir / "md_postprocessor.py"

    if not converter_script.exists():
        return {"error": f"mineru_converter.py not found at {converter_script}"}
    if not postprocessor_script.exists():
        return {"error": f"md_postprocessor.py not found at {postprocessor_script}"}

    repair_results = []
    missing_files = verify_result.get("missing_figures", [])

    if not missing_files:
        return {"repaired": 0, "message": "No files need repair"}

    print(f"\n=== Figure Repair: {len(missing_files)} files to fix ===\n")

    for i, md_name in enumerate(missing_files, 1):
        pdf_path = find_matching_pdf(md_name, pdf_dir)

        if pdf_path is None:
            result = {
                "file": md_name,
                "status": "skip",
                "reason": "No matching PDF found"
            }
            print(f"[{i}/{len(missing_files)}] SKIP: {md_name} (no PDF)")
            repair_results.append(result)
            continue

        print(f"[{i}/{len(missing_files)}] Reconverting: {pdf_path.name}")

        # MinerU 재변환
        try:
            cmd = [
                sys.executable, str(converter_script),
                "--single", str(pdf_path),
                "--output-dir", str(md_dir),
                "-b", "pipeline"
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )

            if proc.returncode != 0:
                result = {
                    "file": md_name,
                    "status": "convert_failed",
                    "error": proc.stderr[:500]
                }
                print(f"  -> FAILED: conversion error")
                repair_results.append(result)
                continue

            # 변환 결과 파싱
            try:
                conv_result = json.loads(proc.stdout)
                figures = conv_result.get("figures", 0)
            except json.JSONDecodeError:
                figures = "unknown"

        except subprocess.TimeoutExpired:
            result = {
                "file": md_name,
                "status": "timeout",
                "error": "MinerU conversion timed out (600s)"
            }
            print(f"  -> FAILED: timeout")
            repair_results.append(result)
            continue

        result = {
            "file": md_name,
            "status": "repaired",
            "pdf_used": pdf_path.name,
            "figures": figures
        }
        print(f"  -> OK: {figures} figures")
        repair_results.append(result)

    # 일괄 postprocessor 적용
    if any(r["status"] == "repaired" for r in repair_results):
        print(f"\nApplying postprocessor to all files...")
        try:
            cmd = [
                sys.executable, str(postprocessor_script),
                "--input-dir", str(md_dir),
                "--output-dir", str(md_dir)
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            print("Postprocessor applied successfully")
        except Exception as e:
            print(f"Postprocessor warning: {e}")

    # 복구 후 재검증
    print("\n=== Post-repair verification ===")
    post_verify = verify_md_dir(md_dir)

    return {
        "repairs": repair_results,
        "repaired_count": sum(1 for r in repair_results if r["status"] == "repaired"),
        "skip_count": sum(1 for r in repair_results if r["status"] == "skip"),
        "failed_count": sum(1 for r in repair_results if r["status"] in ("convert_failed", "timeout")),
        "post_verify": {
            "files_with_figures": post_verify["files_with_figures"],
            "files_without_figures": post_verify["files_without_figures"],
            "total_image_refs": post_verify["total_image_refs"],
            "still_missing": post_verify["missing_figures"]
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify and repair figure references in converted MD files"
    )
    parser.add_argument(
        "--md-dir", "-m",
        type=Path,
        required=True,
        help="Directory containing converted MD files"
    )
    parser.add_argument(
        "--pdf-dir", "-p",
        type=Path,
        default=None,
        help="Directory containing original PDF files (required for repair mode)"
    )
    parser.add_argument(
        "--mode",
        choices=["verify", "repair"],
        default="verify",
        help="verify: check only, repair: check and fix (default: verify)"
    )
    parser.add_argument(
        "--check-images",
        action="store_true",
        help="Also verify that referenced image files exist on disk"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON report path (default: print to stdout)"
    )

    args = parser.parse_args()

    if not args.md_dir.exists():
        print(f"Error: MD directory not found: {args.md_dir}")
        return 1

    # Step 1: 검증
    print(f"=== Figure Verification: {args.md_dir} ===\n")
    verify_result = verify_md_dir(args.md_dir, args.check_images)

    print(f"Total files: {verify_result['total_files']}")
    print(f"With figures: {verify_result['files_with_figures']}")
    print(f"Without figures: {verify_result['files_without_figures']}")
    print(f"Total image refs: {verify_result['total_image_refs']}")

    if verify_result["missing_figures"]:
        print(f"\nFiles missing figures:")
        for f in verify_result["missing_figures"]:
            print(f"  - {f}")

    report = {"verification": verify_result}

    # Step 2: 복구 (repair 모드)
    if args.mode == "repair" and verify_result["files_without_figures"] > 0:
        if args.pdf_dir is None:
            print("\nError: --pdf-dir is required for repair mode")
            return 1
        if not args.pdf_dir.exists():
            print(f"\nError: PDF directory not found: {args.pdf_dir}")
            return 1

        script_dir = Path(__file__).parent
        repair_result = repair_missing_figures(
            args.md_dir, args.pdf_dir, verify_result, script_dir
        )
        report["repair"] = repair_result

        print(f"\n=== Repair Summary ===")
        print(f"Repaired: {repair_result['repaired_count']}")
        print(f"Skipped: {repair_result['skip_count']}")
        print(f"Failed: {repair_result['failed_count']}")
        if repair_result.get("post_verify", {}).get("still_missing"):
            print(f"Still missing: {repair_result['post_verify']['still_missing']}")
    elif args.mode == "repair" and verify_result["files_without_figures"] == 0:
        print("\nAll files have figure references. No repair needed.")

    # 리포트 출력
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"\nReport saved: {args.output}")
    else:
        print(f"\n{json.dumps(report, indent=2, ensure_ascii=False)}")

    # 종료 코드: 누락 파일이 있으면 1
    if verify_result["files_without_figures"] > 0 and args.mode == "verify":
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
