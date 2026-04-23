#!/usr/bin/env python3
"""
Markdown Post-processor (General-purpose)

MinerU로 변환된 Markdown을 후처리하여 깨끗한 표준 MD로 정리합니다.
학술 논문, 기술 문서, 보고서 등 모든 종류의 문서를 지원합니다.

Usage:
    # 배치 모드 (폴더 내 모든 MD 처리)
    python md_postprocessor.py --input-dir ./converted/ --output-dir ./processed/

    # 단일 파일 모드
    python md_postprocessor.py --single ./document.md --output ./processed/document.md

Features:
    - 선행 점(.) 제거 및 번호 목록 헤더 수정
    - HTML 표 → Markdown 표 변환
    - 수식 정리
    - 불필요한 아티팩트 제거
    - 이미지 경로 공백 처리 (angle brackets)
"""

import argparse
import re
from pathlib import Path
from typing import Tuple


def clean_leading_dots_in_headers(content: str) -> str:
    """헤더 앞의 점(.) 제거: '# .Introduction' → '# Introduction'"""
    return re.sub(r'^(#+\s*)\.\s*', r'\1', content, flags=re.MULTILINE)


def fix_numbered_list_headers(content: str) -> str:
    """번호 목록이 잘못 헤더로 파싱된 경우 수정

    MinerU가 '2. Variable Geometry...'를 '# 2. Variable Geometry...'로
    파싱하는 경우, 번호 접두사를 제거하고 적절한 하위 헤더로 변환
    """
    lines = content.split('\n')
    result = []

    for line in lines:
        stripped = line.strip()
        # '# 숫자' 또는 '# 숫자텍스트' 패턴 감지 (예: '# 2. VGT', '# 32-stage')
        match = re.match(r'^#\s+(\d+)(\.\s*|\s+)(.+)$', stripped)
        if match:
            num = match.group(1)
            text = match.group(3)
            # 실제 섹션 번호인지 판단 (1~9의 단일 숫자이고 텍스트가 대문자 시작)
            if len(num) == 1 and int(num) <= 9 and text[0].isupper():
                result.append(f'## {num}. {text}')
            else:
                result.append(line)
        else:
            result.append(line)

    return '\n'.join(result)


def normalize_section_headers(content: str) -> str:
    """섹션 헤더 정리: 선행 점 제거 + 번호 목록 헤더 수정"""
    content = clean_leading_dots_in_headers(content)
    content = fix_numbered_list_headers(content)
    return content


def clean_equations(content: str) -> str:
    """수식 정리 (display 수식 블록 앞뒤 빈 줄 보장).

    주의: `\\s+` 는 줄바꿈을 포함하므로 `$` 주변 `\\s+` 를 전부 제거하면
    display 수식 `$$...$$` 의 줄바꿈이 사라지고 본문과 수식이 한 줄에 달라붙는다.
    또한 Obsidian 등 일부 렌더러는 `text $...$ text` 처럼 `$` 주변 공백이 있어야
    인라인 수식을 올바르게 인식하므로, 주변 공백을 함부로 깎지 않는다.
    """
    # display 수식이 직전 본문과 한 줄에 붙어 있으면 빈 줄을 삽입
    content = re.sub(r'(\S)\n\$\$', r'\1\n\n$$', content)
    content = re.sub(r'\$\$\n(\S)', r'$$\n\n\1', content)
    # display 수식이 본문과 같은 줄에 혼재되어 있으면 줄바꿈으로 분리
    #   (MinerU 가 때때로 `... as $$math$$ ...` 형태로 뽑는 경우 방어)
    content = re.sub(
        r'([^\n])\s*\$\$\s*([^\n$][^$]*?)\s*\$\$\s*([^\n])',
        r'\1\n\n$$\n\2\n$$\n\n\3',
        content
    )
    return content


def clean_html_tables(content: str) -> str:
    """HTML <table> 을 Markdown 표로 변환"""

    def _html_table_to_markdown(match):
        table_html = match.group(0)

        # 행 추출
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if not rows:
            return table_html

        md_rows = []
        max_cols = 0

        for row_html in rows:
            # th와 td 셀 추출
            cells = re.findall(r'<(?:th|td)[^>]*>(.*?)</(?:th|td)>', row_html, re.DOTALL)
            # HTML 태그 제거 및 정리
            clean_cells = []
            for cell in cells:
                cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                cell_text = cell_text.replace('|', '\\|')
                cell_text = re.sub(r'\s+', ' ', cell_text)
                clean_cells.append(cell_text)

            if clean_cells:
                md_rows.append(clean_cells)
                max_cols = max(max_cols, len(clean_cells))

        if not md_rows or max_cols == 0:
            return table_html

        # 열 수 정규화
        for row in md_rows:
            while len(row) < max_cols:
                row.append('')

        # Markdown 표 생성
        lines = []
        for i, row in enumerate(md_rows):
            lines.append('| ' + ' | '.join(row) + ' |')
            if i == 0:
                lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')

        return '\n'.join(lines)

    # 모든 <table>...</table> 블록을 변환
    content = re.sub(
        r'<table[^>]*>.*?</table>',
        _html_table_to_markdown,
        content,
        flags=re.DOTALL
    )

    return content


def clean_tables(content: str) -> str:
    """표 정리 (HTML 표 변환 후 Markdown 표 정리)"""

    # HTML 표를 먼저 Markdown으로 변환
    content = clean_html_tables(content)

    # Markdown 표 정리
    content = re.sub(r'\|[\s\-:]+\|', lambda m: re.sub(r'\s+', '', m.group()), content)

    lines = content.split('\n')
    result = []
    in_table = False

    for i, line in enumerate(lines):
        is_table_line = line.strip().startswith('|') and line.strip().endswith('|')

        if is_table_line and not in_table:
            if result and result[-1].strip():
                result.append('')
            in_table = True
        elif not is_table_line and in_table:
            result.append('')
            in_table = False

        result.append(line)

    return '\n'.join(result)


def remove_artifacts(content: str) -> str:
    """변환 아티팩트 제거"""

    content = re.sub(r'^\s*\d+\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'(?<!!)\[\]\([^)]*\)', '', content)
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    content = re.sub(r'^.*?(doi|DOI):\s*\S+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^.*?www\.\S+\.(com|org|edu).*$', '', content, flags=re.MULTILINE)

    return content


def fix_image_paths_with_spaces(content: str) -> str:
    """공백 포함 이미지 경로를 CommonMark angle bracket으로 감싸기

    MinerU 변환 시 MD 파일명과 동일한 이미지 폴더가 생성되는데,
    파일명에 공백이 있으면 Obsidian/Markdown 뷰어에서 이미지가 렌더링되지 않는다.

    Before: ![](path with spaces/images/xxx.jpg)
    After:  ![](<path with spaces/images/xxx.jpg>)
    """
    def _wrap_path(match):
        alt = match.group(1)
        path = match.group(2)
        if ' ' in path and not path.startswith('<'):
            return '![%s](<%s>)' % (alt, path)
        return match.group(0)

    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _wrap_path, content)


def add_section_markers(content: str) -> str:
    """섹션 시작/끝 마커 추가 (분석용)

    범용 문서이므로 모든 ## 레벨 헤딩에 마커를 추가합니다.
    """
    lines = content.split('\n')
    result = []
    current_section = None

    for line in lines:
        match = re.match(r'^##\s+(.+)$', line.strip())
        if match:
            section_name = match.group(1).strip()
            if current_section:
                result.append(f'<!-- SECTION_END: {current_section} -->')
                result.append('')
            current_section = section_name
            result.append(f'<!-- SECTION_START: {section_name} -->')

        result.append(line)

    if current_section:
        result.append(f'<!-- SECTION_END: {current_section} -->')

    return '\n'.join(result)


def process_markdown(content: str, add_markers: bool = False) -> str:
    """Markdown 전체 후처리

    Args:
        content: 원본 Markdown 텍스트
        add_markers: 섹션 마커 추가 여부 (기본: False)
    """
    content = normalize_section_headers(content)
    content = clean_equations(content)
    content = clean_tables(content)
    content = remove_artifacts(content)
    content = fix_image_paths_with_spaces(content)

    if add_markers:
        content = add_section_markers(content)

    return content


def process_file(input_path: Path, output_path: Path, add_markers: bool = False) -> dict:
    """단일 파일 처리"""

    result = {
        "input": str(input_path),
        "output": str(output_path),
        "status": "pending",
        "sections": []
    }

    try:
        content = input_path.read_text(encoding="utf-8")
        processed = process_markdown(content, add_markers)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(processed, encoding="utf-8")

        sections = re.findall(r'^##\s+(.+)$', processed, re.MULTILINE)

        result["status"] = "success"
        result["sections"] = sections

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def batch_process(
    input_dir: Path,
    output_dir: Path,
    add_markers: bool = False
) -> dict:
    """폴더 내 모든 Markdown 파일 처리"""

    output_dir.mkdir(parents=True, exist_ok=True)

    md_files = list(input_dir.glob("*.md"))
    md_files = [f for f in md_files if f.name != "conversion_report.json"]

    print(f"Found {len(md_files)} Markdown files")
    print("-" * 50)

    results = []
    success_count = 0

    for i, md_path in enumerate(md_files, 1):
        print(f"[{i}/{len(md_files)}] Processing: {md_path.name}")

        output_path = output_dir / md_path.name
        result = process_file(md_path, output_path, add_markers)
        results.append(result)

        if result["status"] == "success":
            success_count += 1
            print(f"  -> Sections: {', '.join(result['sections'][:5])}")
        else:
            print(f"  -> Error: {result.get('error', 'Unknown')}")

    print("-" * 50)
    print(f"Processing complete: {success_count}/{len(md_files)} success")

    return {
        "summary": {
            "total": len(md_files),
            "success": success_count,
            "failed": len(md_files) - success_count
        },
        "files": results
    }


def main():
    parser = argparse.ArgumentParser(
        description="Post-process Markdown files converted from PDF"
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=Path,
        default=None,
        help="Directory containing Markdown files (batch mode)"
    )
    parser.add_argument(
        "--single", "-s",
        type=Path,
        default=None,
        help="Single Markdown file path"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Output directory for processed files (batch mode)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (single mode)"
    )
    parser.add_argument(
        "--markers",
        action="store_true",
        help="Add section markers (disabled by default)"
    )

    args = parser.parse_args()

    if not args.input_dir and not args.single:
        parser.error("Either --input-dir or --single is required")

    if args.single:
        if not args.single.exists():
            print(f"Error: File not found: {args.single}")
            return 1
        output_path = args.output or args.single.parent / f"{args.single.stem}_processed.md"
        result = process_file(args.single, output_path, args.markers)
        if result["status"] == "success":
            print(f"Processed: {output_path}")
            print(f"Sections: {', '.join(result['sections'][:5])}")
        else:
            print(f"Error: {result.get('error', 'Unknown')}")
            return 1
    else:
        if not args.input_dir.exists():
            print(f"Error: Input directory not found: {args.input_dir}")
            return 1
        output_dir = args.output_dir or args.input_dir
        batch_process(
            input_dir=args.input_dir,
            output_dir=output_dir,
            add_markers=args.markers
        )

    return 0


if __name__ == "__main__":
    exit(main())
