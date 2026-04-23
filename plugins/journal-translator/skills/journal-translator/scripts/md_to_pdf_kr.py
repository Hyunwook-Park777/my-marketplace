#!/usr/bin/env python3
"""
Korean Markdown to PDF Converter with Embedded Images (ReportLab)

한국어 번역된 학술 논문 Markdown을 이미지 포함 PDF 문서로 변환합니다.

Usage:
    # 단일 파일
    python md_to_pdf_kr.py --input 논문_kr.md --output 논문_kr.pdf --image-base ./md_processed/

    # 배치 모드
    python md_to_pdf_kr.py --input-dir ./translated/ --output-dir ./translated_output/ --image-base ./md_processed/

Features:
    - 한국어 폰트 (맑은 고딕) + 영문 폰트 (Times New Roman)
    - 이미지 자동 삽입 (페이지 폭에 맞춤)
    - Markdown 표 → PDF 표 변환
    - Figure/Table 캡션 중앙 정렬
    - Vancouver 참고문헌 서식
    - A4 페이지, 2.54cm 여백, 1.5 줄간격

Requirements:
    pip install reportlab Pillow
"""

import argparse
import os
import re
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.colors import HexColor, black, grey
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, KeepTogether, PageBreak, LongTable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ── Constants ────────────────────────────────────────────────────────────────
PAGE_WIDTH, PAGE_HEIGHT = A4  # 21cm x 29.7cm
MARGIN = 2.54 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

BODY_SIZE = 11
HEADING1_SIZE = 16
HEADING2_SIZE = 14
HEADING3_SIZE = 12
CAPTION_SIZE = 10
REF_SIZE = 9
LINE_SPACING = 1.5
MAX_IMAGE_WIDTH_CM = 16.0

KR_FONT = "MalgunGothic"
KR_FONT_BOLD = "MalgunGothicBold"
EN_FONT = "Times-Roman"
EN_FONT_BOLD = "Times-Bold"
EN_FONT_ITALIC = "Times-Italic"


# ── Font Registration ────────────────────────────────────────────────────────
def register_korean_fonts():
    """맑은 고딕 TTF 등록 (Regular + Bold)"""
    font_paths = {
        KR_FONT: "C:/Windows/Fonts/malgun.ttf",
        KR_FONT_BOLD: "C:/Windows/Fonts/malgunbd.ttf",
    }
    for name, path in font_paths.items():
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont(name, path))
        else:
            print(f"WARNING: Font not found: {path}")


# ── Styles ───────────────────────────────────────────────────────────────────
def create_styles():
    """한국어 학술 문서 스타일 생성"""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='KR_Body',
        fontName=KR_FONT,
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * LINE_SPACING,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        firstLineIndent=0.75 * cm,
    ))

    styles.add(ParagraphStyle(
        name='KR_BodyNoIndent',
        fontName=KR_FONT,
        fontSize=BODY_SIZE,
        leading=BODY_SIZE * LINE_SPACING,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    ))

    for level, size in [(1, HEADING1_SIZE), (2, HEADING2_SIZE), (3, HEADING3_SIZE)]:
        styles.add(ParagraphStyle(
            name=f'KR_Heading{level}',
            fontName=KR_FONT_BOLD,
            fontSize=size,
            leading=size * 1.4,
            spaceBefore=12 if level == 1 else 8,
            spaceAfter=6,
            alignment=TA_LEFT,
        ))

    styles.add(ParagraphStyle(
        name='KR_Caption',
        fontName=KR_FONT,
        fontSize=CAPTION_SIZE,
        leading=CAPTION_SIZE * LINE_SPACING,
        alignment=TA_CENTER,
        spaceAfter=8,
        spaceBefore=4,
    ))

    styles.add(ParagraphStyle(
        name='KR_Reference',
        fontName=KR_FONT,
        fontSize=REF_SIZE,
        leading=REF_SIZE * 1.4,
        alignment=TA_LEFT,
        spaceAfter=2,
        leftIndent=1.0 * cm,
    ))

    styles.add(ParagraphStyle(
        name='KR_Blockquote',
        fontName=KR_FONT,
        fontSize=BODY_SIZE - 1,
        leading=(BODY_SIZE - 1) * LINE_SPACING,
        alignment=TA_LEFT,
        leftIndent=1.0 * cm,
        spaceAfter=4,
        textColor=HexColor('#333333'),
    ))

    styles.add(ParagraphStyle(
        name='KR_ImageMissing',
        fontName=KR_FONT,
        fontSize=CAPTION_SIZE,
        leading=CAPTION_SIZE * 1.4,
        alignment=TA_CENTER,
        textColor=HexColor('#999999'),
        spaceAfter=6,
    ))

    return styles


# ── Inline Parsing ───────────────────────────────────────────────────────────
def escape_xml(text: str) -> str:
    """XML 특수문자 이스케이프 (ReportLab Paragraph용)"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


def parse_inline_to_html(text: str) -> str:
    """Markdown 인라인 서식 → ReportLab HTML 태그 변환

    **bold** → <b>bold</b>
    *italic* → <i>italic</i>
    [1,2] → [1,2] (citation, 그대로 유지)
    """
    # 먼저 XML 이스케이프 (& < > 처리)
    text = escape_xml(text)

    # **bold** → <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # *italic* → <i>italic</i>
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)

    return text


# ── Image Handling ───────────────────────────────────────────────────────────
def find_image_file(image_ref: str, image_base: Path, md_stem: str) -> Optional[Path]:
    """이미지 파일 경로를 다양한 위치에서 탐색 (md_to_docx_kr.py 로직 재사용)"""
    clean_ref = image_ref.strip('<>')

    # 1. 직접 경로
    direct = image_base / clean_ref
    if direct.exists():
        return direct

    # 2. stem 기반 (_kr 제거)
    orig_stem = md_stem
    if orig_stem.endswith('_kr'):
        orig_stem = orig_stem[:-3]

    filename = Path(clean_ref).name

    for stem in [orig_stem, md_stem]:
        candidate = image_base / stem / "images" / filename
        if candidate.exists():
            return candidate

    # 3. images/ 직접
    candidate = image_base / "images" / filename
    if candidate.exists():
        return candidate

    # 4. 하위 폴더 탐색
    for img_dir in image_base.rglob("images"):
        candidate = img_dir / filename
        if candidate.exists():
            return candidate

    return None


def create_rl_image(image_path: Path) -> Optional[RLImage]:
    """이미지를 ReportLab Image 객체로 변환 (페이지 폭에 맞춤)"""
    try:
        from PIL import Image as PILImage
        with PILImage.open(str(image_path)) as img:
            w_px, h_px = img.size

        if w_px == 0 or h_px == 0:
            return None

        # DPI 기본값 96
        w_inches = w_px / 96.0
        h_inches = h_px / 96.0

        max_w = MAX_IMAGE_WIDTH_CM * cm

        # 페이지 폭에 맞춤
        w_pt = w_inches * inch
        h_pt = h_inches * inch

        if w_pt > max_w:
            ratio = max_w / w_pt
            w_pt *= ratio
            h_pt *= ratio

        # 극단적 비율 이미지 (수식 등): 최소 높이 보장
        if h_pt < 0.3 * inch:
            h_pt = 0.3 * inch

        # 페이지 높이의 80% 초과 시 축소
        max_h = (PAGE_HEIGHT - 2 * MARGIN) * 0.8
        if h_pt > max_h:
            ratio = max_h / h_pt
            w_pt *= ratio
            h_pt *= ratio

        rl_img = RLImage(str(image_path), width=w_pt, height=h_pt)
        rl_img.hAlign = 'CENTER'
        return rl_img

    except ImportError:
        rl_img = RLImage(str(image_path), width=max_w)
        rl_img.hAlign = 'CENTER'
        return rl_img
    except Exception:
        return None


# ── Abstract Table Handling ───────────────────────────────────────────────────
def is_abstract_table(table_lines: list) -> bool:
    """초록/논문정보 표인지 감지"""
    if not table_lines:
        return False
    first_line = table_lines[0].lower()
    has_info = any(kw in first_line for kw in [
        '논문 정보', '논 문 정 보', '논문정보', 'article info',
    ])
    has_abstract = any(kw in first_line for kw in [
        '초 록', '초록', 'abstract',
    ])
    return has_info and has_abstract


def parse_abstract_table(table_lines: list) -> dict:
    """초록 표에서 논문 정보 라벨, 키워드, 초록 본문 추출"""
    result = {'info_label': '논문 정보', 'keywords': [], 'abstract_label': '초록',
              'abstract': ''}

    rows = parse_markdown_table(table_lines)
    if not rows:
        return result

    first_row = rows[0]
    if first_row:
        info_cell = first_row[0]
        parts = re.split(r'<br\s*/?>', info_cell)
        if parts:
            result['info_label'] = parts[0].strip()
        for part in parts[1:]:
            part = part.strip()
            if not part:
                continue
            if re.match(r'^(키워드|keywords?)\s*:?\s*$', part, re.IGNORECASE):
                continue
            result['keywords'].append(part)

        for cell in first_row[1:]:
            cell = cell.strip()
            if cell and '---' not in cell:
                result['abstract_label'] = cell
                break

    for row in rows[1:]:
        for cell in row:
            cell = cell.strip()
            if cell and len(cell) > len(result['abstract']):
                result['abstract'] = cell

    return result


def render_abstract_flowables(info: dict, styles) -> list:
    """초록/논문정보를 PDF flowable 리스트로 변환"""
    flowables = []

    # 키워드
    if info['keywords']:
        kw_text = '<b>키워드: </b>' + escape_xml(', '.join(info['keywords']))
        flowables.append(Paragraph(kw_text, styles['KR_BodyNoIndent']))

    # 초록 제목
    if info['abstract']:
        html_label = parse_inline_to_html(info['abstract_label'])
        flowables.append(Paragraph(html_label, styles['KR_Heading2']))
        # 초록 본문
        html_body = parse_inline_to_html(info['abstract'])
        flowables.append(Paragraph(html_body, styles['KR_Body']))

    return flowables


# ── Table Handling ───────────────────────────────────────────────────────────
def parse_markdown_table(lines: list) -> list:
    """Markdown 표를 2D 리스트로 파싱"""
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith('|') or not line.endswith('|'):
            continue
        if re.match(r'^\|[\s\-:]+\|', line):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        rows.append(cells)
    return rows


def create_pdf_table(rows: list, styles) -> Optional[list]:
    """Markdown 표 데이터 → ReportLab Table 또는 텍스트 폴백 리스트

    Returns a list of flowables (Table or Paragraphs for oversized tables).
    """
    if not rows:
        return None

    n_cols = max(len(r) for r in rows)

    # 63열 초과 시 텍스트 폴백
    if n_cols > 63:
        return None

    # 셀 내용을 Paragraph로 변환
    cell_style = ParagraphStyle(
        name='TableCell',
        fontName=KR_FONT,
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
    )
    header_style = ParagraphStyle(
        name='TableHeader',
        fontName=KR_FONT_BOLD,
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
    )

    # 매우 긴 셀(500자 초과)이 있으면 텍스트 폴백
    max_cell_len = 0
    for row_data in rows:
        for cell in row_data:
            max_cell_len = max(max_cell_len, len(cell))

    if max_cell_len > 500:
        # 긴 표 → 텍스트 폴백 (페이지 넘침 방지)
        body_style = ParagraphStyle(
            name='TableFallback',
            fontName=KR_FONT,
            fontSize=BODY_SIZE - 1,
            leading=(BODY_SIZE - 1) * LINE_SPACING,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        )
        flowables = []
        for row_data in rows:
            for cell in row_data:
                cell = cell.strip()
                if cell:
                    html = parse_inline_to_html(cell)
                    flowables.append(Paragraph(html, body_style))
        return flowables if flowables else None

    table_data = []
    for i, row_data in enumerate(rows):
        row = []
        for j in range(n_cols):
            cell_text = row_data[j] if j < len(row_data) else ""
            cell_text = parse_inline_to_html(cell_text)
            st = header_style if i == 0 else cell_style
            row.append(Paragraph(cell_text, st))
        table_data.append(row)

    # 열 폭 자동 계산
    col_width = CONTENT_WIDTH / n_cols
    col_widths = [col_width] * n_cols

    table = LongTable(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, black),
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#E8E8E8')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    table.hAlign = 'CENTER'
    return [table]


# ── Main Converter ───────────────────────────────────────────────────────────
def convert_md_to_pdf_kr(
    input_path: Path,
    output_path: Path,
    image_base: Optional[Path] = None
) -> dict:
    """한국어 Markdown → PDF 변환"""
    content = input_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    md_stem = input_path.stem

    if image_base is None:
        image_base = input_path.parent

    styles = create_styles()
    story = []

    result = {
        "input": str(input_path),
        "output": str(output_path),
        "status": "pending",
        "paragraphs": 0,
        "headings": 0,
        "images_inserted": 0,
        "images_missing": 0,
        "tables": 0,
        "references": 0,
        "warnings": []
    }

    in_references = False
    in_table = False
    table_lines = []
    paragraph_buffer = []
    in_code_block = False

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            text = ' '.join(paragraph_buffer).strip()
            if text:
                html_text = parse_inline_to_html(text)
                if in_references:
                    story.append(Paragraph(html_text, styles['KR_Reference']))
                else:
                    story.append(Paragraph(html_text, styles['KR_Body']))
                result["paragraphs"] += 1
            paragraph_buffer = []

    def flush_table():
        nonlocal table_lines, in_table
        if table_lines:
            if is_abstract_table(table_lines):
                info = parse_abstract_table(table_lines)
                abs_flowables = render_abstract_flowables(info, styles)
                story.extend(abs_flowables)
                result["paragraphs"] += len(abs_flowables)
            else:
                rows = parse_markdown_table(table_lines)
                if rows:
                    n_cols = max(len(r) for r in rows)
                    if n_cols > 63:
                        for row_data in rows:
                            text = " | ".join(c for c in row_data if c)
                            if text.strip():
                                html = parse_inline_to_html(text)
                                story.append(Paragraph(html, styles['KR_Reference']))
                    else:
                        flowables = create_pdf_table(rows, styles)
                        if flowables:
                            story.append(Spacer(1, 6))
                            story.extend(flowables)
                            story.append(Spacer(1, 6))
                    result["tables"] += 1
            table_lines = []
        in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 코드 블록 건너뛰기
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            i += 1
            continue

        # 빈 줄
        if not stripped:
            if in_table:
                flush_table()
            flush_paragraph()
            i += 1
            continue

        # HTML 주석 건너뛰기
        if stripped.startswith('<!--') and stripped.endswith('-->'):
            i += 1
            continue

        # 표 처리
        if stripped.startswith('|') and stripped.endswith('|'):
            flush_paragraph()
            in_table = True
            table_lines.append(stripped)
            i += 1
            continue
        elif in_table:
            flush_table()

        # 이미지 참조 (독립 행)
        img_match = re.match(r'^!\[([^\]]*)\]\((.+?)\)\s*$', stripped)
        if img_match:
            flush_paragraph()
            img_ref = img_match.group(2)
            img_path = find_image_file(img_ref, image_base, md_stem)
            if img_path:
                rl_img = create_rl_image(img_path)
                if rl_img:
                    story.append(Spacer(1, 4))
                    story.append(rl_img)
                    story.append(Spacer(1, 4))
                    result["images_inserted"] += 1
                else:
                    result["images_missing"] += 1
                    result["warnings"].append(f"Image load failed: {img_ref}")
                    story.append(Paragraph(
                        f"[이미지 삽입 실패: {escape_xml(str(img_path.name))}]",
                        styles['KR_ImageMissing']))
            else:
                result["images_missing"] += 1
                result["warnings"].append(f"Image not found: {img_ref}")
                story.append(Paragraph(
                    f"[이미지 누락: {escape_xml(img_ref)}]",
                    styles['KR_ImageMissing']))
            i += 1
            continue

        # 인라인 이미지 (텍스트 중간에 ![...](...)가 있는 경우)
        if '![' in stripped and not stripped.startswith('!'):
            parts = re.split(r'(!\[[^\]]*\]\([^)]+\))', stripped)
            flush_paragraph()
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                img_inline = re.match(r'^!\[([^\]]*)\]\((.+?)\)$', part)
                if img_inline:
                    img_ref = img_inline.group(2)
                    img_path = find_image_file(img_ref, image_base, md_stem)
                    if img_path:
                        rl_img = create_rl_image(img_path)
                        if rl_img:
                            story.append(rl_img)
                            result["images_inserted"] += 1
                        else:
                            result["images_missing"] += 1
                    else:
                        result["images_missing"] += 1
                else:
                    html = parse_inline_to_html(part)
                    story.append(Paragraph(html, styles['KR_Body']))
                    result["paragraphs"] += 1
            i += 1
            continue

        # 헤더
        header_match = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if header_match:
            flush_paragraph()
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()

            if any(kw in header_text.lower() for kw in ['references', 'reference', '참고문헌']):
                in_references = True

            heading_level = min(level, 3)
            html_text = parse_inline_to_html(header_text)
            story.append(Paragraph(html_text, styles[f'KR_Heading{heading_level}']))
            result["headings"] += 1
            i += 1
            continue

        # Figure/Table 캡션 (중앙 정렬)
        caption_match = re.match(
            r'^\*\*(그림|표|Figure|Table)\s*\d+[\.\):]?\*\*', stripped)
        if caption_match:
            flush_paragraph()
            html_text = parse_inline_to_html(stripped)
            story.append(Paragraph(html_text, styles['KR_Caption']))
            result["paragraphs"] += 1
            i += 1
            continue

        # 블록 인용 (> 로 시작)
        if stripped.startswith('>'):
            flush_paragraph()
            quote_text = stripped.lstrip('>').strip()
            html_text = parse_inline_to_html(quote_text)
            story.append(Paragraph(html_text, styles['KR_Blockquote']))
            result["paragraphs"] += 1
            i += 1
            continue

        # References 섹션
        if in_references:
            flush_paragraph()
            ref_match = re.match(r'^\[?(\d+)\]?\s*(.+)$', stripped)
            if ref_match:
                text = f'[{ref_match.group(1)}] {ref_match.group(2)}'
                html_text = parse_inline_to_html(text)
                story.append(Paragraph(html_text, styles['KR_Reference']))
                result["references"] += 1
            else:
                html_text = parse_inline_to_html(stripped)
                story.append(Paragraph(html_text, styles['KR_Reference']))
            i += 1
            continue

        # 일반 텍스트 (이탤릭 전용 줄 = 저널 헤더/푸터, 무시 가능하지만 포함)
        paragraph_buffer.append(stripped)
        i += 1

    flush_paragraph()
    if in_table:
        flush_table()

    # PDF 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        title=md_stem,
        author="journal-translator",
    )

    try:
        doc.build(story)
        result["status"] = "success"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    return result


# ── Batch Mode ───────────────────────────────────────────────────────────────
def batch_convert(
    input_dir: Path,
    output_dir: Path,
    image_base: Optional[Path] = None
) -> dict:
    """배치 변환"""
    output_dir.mkdir(parents=True, exist_ok=True)
    md_files = sorted(input_dir.glob("*_kr.md"))

    if not md_files:
        md_files = sorted(input_dir.glob("*.md"))

    print(f"Found {len(md_files)} files to convert")
    print("-" * 50)

    results = []
    success = 0

    for idx, md_path in enumerate(md_files, 1):
        print(f"[{idx}/{len(md_files)}] {md_path.name}")
        out_path = output_dir / md_path.with_suffix('.pdf').name

        r = convert_md_to_pdf_kr(md_path, out_path, image_base)
        results.append(r)

        if r["status"] == "success":
            success += 1
            size_kb = out_path.stat().st_size / 1024
            print(f"  -> OK ({size_kb:.0f} KB, {r['images_inserted']} images, "
                  f"{r['tables']} tables, {r['references']} refs)")
            if r["warnings"]:
                for w in r["warnings"][:3]:
                    print(f"  -> WARNING: {w}")
        else:
            print(f"  -> FAILED: {r.get('error', 'Unknown')}")

    print("-" * 50)
    print(f"Complete: {success}/{len(md_files)} converted")

    return {
        "summary": {"total": len(md_files), "success": success,
                     "failed": len(md_files) - success},
        "files": results
    }


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Convert Korean translated Markdown to PDF with images"
    )
    parser.add_argument("--input", "-i", type=Path, default=None,
                        help="Single input MD file")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output .pdf path")
    parser.add_argument("--input-dir", type=Path, default=None,
                        help="Batch: input directory with *_kr.md files")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Batch: output directory")
    parser.add_argument("--image-base", type=Path, default=None,
                        help="Base directory for image lookup")

    args = parser.parse_args()

    # 폰트 등록
    register_korean_fonts()

    if args.input:
        if not args.input.exists():
            print(f"Error: {args.input} not found")
            return 1
        output = args.output or args.input.with_suffix('.pdf')
        r = convert_md_to_pdf_kr(args.input, output, args.image_base)
        print(f"Status: {r['status']}")
        print(f"Paragraphs: {r['paragraphs']}, Headings: {r['headings']}")
        print(f"Images: {r['images_inserted']} inserted, {r['images_missing']} missing")
        print(f"Tables: {r['tables']}, References: {r['references']}")
        if r["warnings"]:
            print("Warnings:")
            for w in r["warnings"]:
                print(f"  - {w}")
    elif args.input_dir:
        if not args.input_dir.exists():
            print(f"Error: {args.input_dir} not found")
            return 1
        out_dir = args.output_dir or args.input_dir / "pdf_output"
        batch_convert(args.input_dir, out_dir, args.image_base)
    else:
        parser.error("Either --input or --input-dir is required")

    return 0


if __name__ == "__main__":
    register_korean_fonts()
    exit(main())
