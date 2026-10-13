#!/usr/bin/env python3
"""
MinerU 4.x engine for mineru_converter.py

MinerU 4.x 는 2.x 와 CLI/출력 구조가 완전히 다르고 의존성(lmdeploy 0.17 등)이 충돌하므로
별도 가상환경에 설치하고 그 Python 으로 `mineru.kit.main parse` 를 호출한다.

  - 품질은 `--tier` (flash / basic / standard / advanced) 로 고른다. `-l` / `-d` 옵션은 없다.
  - `--format zip` 으로 받아 markdown.md + images/ 를 꺼낸다. 기본 markdown 형식은 이미지를
    base64 로 MD 에 넣어 Obsidian 볼트가 수십 MB 로 커지기 때문이다.
  - 결과는 2.x 엔진과 같은 구조로 정리한다: {output_dir}/{stem}.md + {output_dir}/{stem}/images/

4.x 가상환경 Python 탐색 순서: --mineru4-python > 환경변수 MINERU4_PYTHON > ~/venvs/mineru4
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

from mineru_converter import (
    MAX_PATH_WINDOWS,
    _get_short_temp_dir,
    extract_sections,
    get_pdf_page_count,
    mineru_error_hint,
    verify_image_references,
)

MINERU4_TIERS = ["flash", "basic", "standard", "advanced"]
DEFAULT_TIER = "advanced"
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def find_mineru4_python(explicit: Optional[str] = None) -> Optional[Path]:
    """MinerU 4.x 가 설치된 가상환경의 python 실행 파일을 찾는다 (없으면 None)."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("MINERU4_PYTHON"):
        candidates.append(Path(os.environ["MINERU4_PYTHON"]))
    home = Path.home()
    candidates += [home / "venvs/mineru4/Scripts/python.exe", home / "venvs/mineru4/bin/python"]
    for py in candidates:
        if py.is_file():
            return py
    return None


def probe_mineru4(python: Path) -> dict:
    """MinerU 4.x 버전과 CUDA 가용 여부 확인."""
    code = ("import json, torch, importlib.metadata as m;"
            "print(json.dumps({'version': m.version('mineru'), 'cuda': torch.cuda.is_available()}))")
    proc = None
    try:
        # stdin 을 닫아 두어 python 이 아닌 실행 파일을 지정해도 입력 대기로 멈추지 않게 한다
        proc = subprocess.run([str(python), "-c", code], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace", env=UTF8_ENV, timeout=120)
        info = json.loads(proc.stdout.strip().splitlines()[-1])
        info["ok"] = int(info["version"].split(".")[0]) >= 4
        return info
    except Exception as e:
        detail = (proc.stderr or "").strip().splitlines()[-1:] if proc else []
        return {"ok": False, "error": f"{e}" + (f" / {detail[0][-300:]}" if detail else "")}


def _extract_zip(zip_path: Path, output_dir: Path, stem: str) -> tuple:
    """zip 의 markdown.md / images/ 를 {stem}.md / {stem}/images/ 로 옮기고 참조를 고친다.

    Returns: (md_path, warnings)
    """
    warnings = []
    final_md = output_dir / f"{stem}.md"
    images_dir = output_dir / stem / "images"
    # 재변환 시 이전 엔진/이름 규칙의 이미지가 고아 파일로 남지 않게 비운다
    if images_dir.is_dir():
        shutil.rmtree(str(images_dir), ignore_errors=True)
    with zipfile.ZipFile(zip_path) as zf:
        content = zf.read("markdown.md").decode("utf-8")
        image_names = [n for n in zf.namelist() if n.startswith("images/") and not n.endswith("/")]
        if image_names:
            images_dir.mkdir(parents=True, exist_ok=True)
            longest = max(len(str(images_dir.resolve() / Path(n).name)) for n in image_names)
            rename = longest >= MAX_PATH_WINDOWS
            if rename:
                warnings.append("Image files renamed to img_NNN to fit Windows MAX_PATH")
            for i, name in enumerate(sorted(image_names), 1):
                # 하위 폴더가 있어도 평탄하게 저장 (Path.name 으로 zip-slip 도 차단)
                new_name = f"img_{i:03d}{Path(name).suffix}" if rename else Path(name).name
                (images_dir / new_name).write_bytes(zf.read(name))
                rel = name[len("images/"):]
                if rel != new_name:
                    for a, b in ((f"](images/{rel})", f"](images/{new_name})"),
                                 (f'src="images/{rel}"', f'src="images/{new_name}"')):
                        content = content.replace(a, b)
    # images/... → {stem}/images/... (Markdown 이미지와 HTML 표 안의 <img> 모두)
    content = content.replace("](images/", f"]({stem}/images/").replace('src="images/', f'src="{stem}/images/')
    final_md.write_text(content, encoding="utf-8")
    return final_md, warnings


def convert_with_mineru4(
    pdf_paths: list,
    output_dir: Path,
    python: Path,
    tier: str = DEFAULT_TIER,
    ocr_mode: str = "auto",
    pages: Optional[str] = None,
    timeout: int = 3600,
) -> list:
    """PDF 여러 개를 MinerU 4.x 로 한 번에 변환 (모델은 한 번만 로드).

    MAX_PATH 와 비ASCII 경로 문제를 피하려고 짧은 임시 폴더에 해시 이름으로 복사해 변환한다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = _get_short_temp_dir()
    results = []
    try:
        tmp_in, tmp_out = tmp_dir / "in", tmp_dir / "out"
        tmp_in.mkdir()
        tmp_out.mkdir()
        names = {}
        for pdf in pdf_paths:
            short = hashlib.md5(str(pdf.resolve()).encode("utf-8")).hexdigest()[:8]
            shutil.copy2(str(pdf), str(tmp_in / f"{short}.pdf"))
            names[short] = pdf

        cmd = [str(python), "-m", "mineru.kit.main", "parse", str(tmp_in), "-o", str(tmp_out),
               "--tier", tier, "--format", "zip", "--ocr-mode", ocr_mode]
        if pages:
            cmd += ["--pages", pages]
        # --single 모드의 stdout 은 JSON 전용이므로 진행 메시지는 stderr 로
        print(f"MinerU 4 ({tier}): {len(pdf_paths)} file(s)", file=sys.stderr)
        error = None
        stderr = ""
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  env=UTF8_ENV, timeout=timeout * max(1, len(pdf_paths)))
            stderr = proc.stderr + proc.stdout
            if proc.returncode != 0:
                error = f"mineru-kit exited with code {proc.returncode}"
        except subprocess.TimeoutExpired:
            error = f"Conversion timed out ({timeout}s per file)"
        hint = mineru_error_hint(stderr)

        for short, pdf in names.items():
            result = {
                "input": str(pdf), "output": None, "status": "failed", "engine": f"mineru4:{tier}",
                "pages": get_pdf_page_count(pdf), "sections_found": [], "figures": 0, "tables": 0,
                "equations": 0, "warnings": [], "error": None,
            }
            zip_path = tmp_out / f"{short}.zip"
            if zip_path.exists():
                # 한 파일의 zip 이 깨져도(markdown.md 없음, 손상, 경로 초과) 나머지 파일과 리포트는 살린다
                try:
                    md, warns = _extract_zip(zip_path, output_dir, pdf.stem)
                    content = md.read_text(encoding="utf-8")
                    body = re.sub(r"<details\b.*?</details>", "", content, flags=re.DOTALL | re.IGNORECASE)
                    result.update({
                        "output": str(md), "status": "success",
                        "sections_found": extract_sections(content),
                        "figures": len(re.findall(r"!\[", content)),
                        "tables": body.lower().count("<table") + len(re.findall(r"(?m)^\|[ :|-]+\|$", body)),
                        "equations": content.count("$$") // 2 + (content.count("$") - 2 * content.count("$$")) // 2,
                        "warnings": warns,
                    })
                    missing = verify_image_references(md, output_dir)
                    if missing:
                        result["warnings"].append(f"Missing {len(missing)} image(s): {', '.join(missing[:3])}")
                except Exception as e:
                    result["error"] = f"zip extraction failed: {type(e).__name__}: {e}"
            else:
                result["error"] = (error or "Output zip not created") + (f" (MinerU: {hint})" if hint else "")
            results.append(result)
    finally:
        shutil.rmtree(str(tmp_dir), ignore_errors=True)
    return results
