#!/usr/bin/env python3
"""
ISO Document Clause Parser

ISO 표준 문서(Markdown)에서 조항(clause) 구조를 파싱하여 JSON으로 출력합니다.
pymupdf4llm으로 변환된 Markdown 형식을 기본 지원합니다.

Usage:
    python clause_parser.py <md_file> -o <output.json>
    python clause_parser.py <md_file>  # stdout으로 출력

지원하는 조항 패턴:
    - 숫자 조항: ## **4 Symbols**, ## **4.1 General**, ## **4.1.1 Detail**
    - 용어 정의: ## **3.1** (다음 줄에 ## **accuracy**)
    - 부속서: ## **Annex A**, ## **Annex B** (informative)
    - 비고/예시: NOTE, NOTE 1, EXAMPLE
"""

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Clause:
    number: str
    title: str
    level: int
    content: str = ""
    notes: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    subclauses: list = field(default_factory=list)
    parent: Optional[str] = None


def strip_bold(text: str) -> str:
    """Markdown 볼드 마커(**) 제거"""
    return text.replace('**', '').strip()


# pymupdf4llm 형식: ## **5.1 Principle of emission measurement**
# 볼드 감싸진 조항 번호+제목
# 단독 대문자(A, B, C)는 허용하지 않음 — 그림 레이블 오탐 방지
# Annex 하위 조항(A.1, B.2.3)은 허용
BOLD_CLAUSE_RE = re.compile(
    r'^#{1,6}\s+\*\*'
    r'('
    r'[A-Z]\.\d+(?:\.\d+)*'     # Annex sub-clause: A.1, A.1.1 (not standalone A)
    r'|'
    r'\d+(?:\.\d+)*'            # numeric clause: 4, 4.1, 4.1.1
    r')'
    r'\s+'                       # space after number
    r'(.+?)'                     # title
    r'\*\*\s*$'                  # closing bold
)

# 번호만 있는 헤더: ## **3.1** (용어 정의 등에서 제목이 다음 줄)
# 단독 대문자 제외
BOLD_NUMBER_ONLY_RE = re.compile(
    r'^#{1,6}\s+\*\*'
    r'('
    r'[A-Z]\.\d+(?:\.\d+)*'
    r'|'
    r'\d+(?:\.\d+)*'
    r')'
    r'\*\*\s*$'
)

# 볼드 제목 헤더: ## **accuracy** (번호 없이 제목만)
BOLD_TITLE_ONLY_RE = re.compile(
    r'^#{1,6}\s+\*\*([^*\d][^*]*?)\*\*\s*$'
)

# 비볼드 조항 패턴 (일반 MD)
# 단독 대문자 제외
PLAIN_CLAUSE_RE = re.compile(
    r'^#{1,6}\s+'
    r'('
    r'[A-Z]\.\d+(?:\.\d+)*'
    r'|'
    r'\d+(?:\.\d+)*'
    r')'
    r'\s+'
    r'(.+?)$'
)

# 부속서 패턴: ## **Annex A** 또는 ## **Annex B** (informative)
ANNEX_RE = re.compile(
    r'^#{1,6}\s+\*?\*?'
    r'(?:Annex|ANNEX)\s+'
    r'([A-Z])'
    r'\*?\*?'
    r'(?:\s*\*?\*?\((\w+)\)\*?\*?)?'   # optional (informative)/(normative)
    r'(?:\s*[-—]\s*(.+))?'
    r'\s*$'
)

# 페이지 아티팩트 필터링
PAGE_NUMBER_RE = re.compile(r'^\*\*\d+\*\*\s*$')
COPYRIGHT_RE = re.compile(r'^©\s+ISO\s+\d{4}')
DOC_HEADER_RE = re.compile(r'^\*\*ISO[/ ].*?:\d{4}.*?\*\*\s*$')

# NOTE 패턴
NOTE_RE = re.compile(
    r'^(?:NOTE|Note)\s*(\d*)\s*(?:to entry)?[\s:—-]*(.*)',
    re.IGNORECASE
)

# EXAMPLE 패턴
EXAMPLE_RE = re.compile(
    r'^(?:EXAMPLE|Example)\s*(\d*)[\s:—-]*(.*)',
    re.IGNORECASE
)


def get_clause_level(number: str) -> int:
    """조항 번호의 깊이를 반환. 예: '4' → 1, '4.1' → 2, '4.1.1' → 3"""
    return len(number.split('.'))


def get_parent_number(number: str) -> Optional[str]:
    """상위 조항 번호를 반환. 예: '4.1.1' → '4.1', '4' → None"""
    parts = number.split('.')
    if len(parts) <= 1:
        return None
    return '.'.join(parts[:-1])


def is_artifact_line(stripped: str) -> bool:
    """페이지 번호, 저작권, 문서 헤더 등 아티팩트인지 판별"""
    if PAGE_NUMBER_RE.match(stripped):
        return True
    if COPYRIGHT_RE.match(stripped):
        return True
    if DOC_HEADER_RE.match(stripped):
        return True
    # "Published in Switzerland", "All rights reserved" 등
    if stripped in ('Published in Switzerland',):
        return True
    if '– All rights reserved' in stripped:
        return True
    # 빈 표 참조 아티팩트
    if stripped == '**==> picture' or 'intentionally omitted <==' in stripped:
        return True
    return False


def parse_document_title(lines: list) -> str:
    """문서 제목을 추출"""
    for line in lines[:30]:
        stripped = line.strip()
        clean = strip_bold(stripped).lstrip('# ').strip()
        if 'ISO' in clean and ('8178' in clean or 'IATF' in clean or 'DIS' in clean):
            return clean
        if clean.startswith('Reciprocating') or clean.startswith('Road vehicles'):
            return clean
    # 폴백: ISO 번호 찾기
    for line in lines[:30]:
        stripped = strip_bold(line.strip())
        if re.match(r'ISO[/ ][\d-]+', stripped):
            return stripped
    return "Unknown ISO Document"


def parse_clauses(text: str) -> dict:
    """
    ISO Markdown 문서를 파싱하여 조항 구조를 반환.

    pymupdf4llm 출력 형식을 기본 지원:
    - ## **5.1 Title** (번호+제목 볼드)
    - ## **3.1** + ## **accuracy** (번호/제목 분리)
    - ## **Annex A** (부속서)
    """
    lines = text.split('\n')
    document_title = parse_document_title(lines)

    clauses = {}  # number -> Clause
    current_clause = None
    current_note = None
    current_example = None
    content_buffer = []
    pending_number = None  # 번호만 나온 경우, 다음 줄에서 제목을 기다림
    in_toc = False  # TOC 영역 스킵

    def flush_content():
        nonlocal content_buffer, current_note, current_example
        if current_clause is None:
            content_buffer = []
            return
        # 아티팩트 라인 제거
        clean_lines = [l for l in content_buffer if not is_artifact_line(l.strip())]
        text = '\n'.join(clean_lines).strip()
        if current_note is not None:
            if text:
                current_clause.notes.append(text)
            current_note = None
        elif current_example is not None:
            if text:
                current_clause.examples.append(text)
            current_example = None
        else:
            if current_clause.content:
                current_clause.content += '\n' + text
            else:
                current_clause.content = text
        content_buffer = []

    def register_clause(number: str, title: str):
        nonlocal current_clause
        flush_content()
        level = get_clause_level(number)
        parent = get_parent_number(number)

        clause = Clause(
            number=number,
            title=title,
            level=level,
            parent=parent,
        )
        clauses[number] = clause
        current_clause = clause

        # 부모 조항에 하위 조항 등록
        if parent and parent in clauses:
            if number not in clauses[parent].subclauses:
                clauses[parent].subclauses.append(number)

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 빈 줄
        if not stripped:
            if pending_number is None:
                content_buffer.append(line)
            continue

        # 아티팩트 라인 스킵
        if is_artifact_line(stripped):
            continue

        # TOC 영역 감지 및 스킵
        if stripped == '## **Contents**' or stripped == '**Contents**':
            in_toc = True
            continue
        if in_toc:
            # TOC는 보통 Foreword 또는 1 Scope 전까지
            if re.match(r'^#{1,6}\s+\*\*(?:Foreword|Introduction|1\s)', stripped):
                in_toc = False
            else:
                continue

        # 번호만 있는 헤더 대기 중일 때 제목 매칭
        if pending_number is not None:
            title_match = BOLD_TITLE_ONLY_RE.match(stripped)
            if title_match:
                title = strip_bold(title_match.group(1))
                register_clause(pending_number, title)
                pending_number = None
                continue
            else:
                # 제목이 안 나오면 번호만으로 등록
                register_clause(pending_number, "(untitled)")
                pending_number = None
                # 이 줄은 다시 처리 필요 — 아래로 fall through

        # 부속서 감지: ## **Annex A** (informative)
        annex_match = ANNEX_RE.match(stripped)
        if annex_match:
            flush_content()
            letter = annex_match.group(1)
            annex_type = annex_match.group(2) or ""
            annex_title = annex_match.group(3) or ""
            full_title = f"Annex {letter}"
            if annex_type:
                full_title += f" ({annex_type})"
            if annex_title:
                full_title += f" - {strip_bold(annex_title)}"

            clause = Clause(number=letter, title=full_title, level=1)
            clauses[letter] = clause
            current_clause = clause
            continue

        # 볼드 번호+제목: ## **5.1 Principle of emission measurement**
        bold_match = BOLD_CLAUSE_RE.match(stripped)
        if bold_match:
            number = bold_match.group(1)
            title = strip_bold(bold_match.group(2))
            # 유효성: 첫 세그먼트가 99 이하
            if number[0].isdigit():
                try:
                    if int(number.split('.')[0]) > 99:
                        content_buffer.append(line)
                        continue
                except ValueError:
                    pass
            register_clause(number, title)
            continue

        # 볼드 번호만: ## **3.1** (제목은 다음 줄)
        num_only_match = BOLD_NUMBER_ONLY_RE.match(stripped)
        if num_only_match:
            number = num_only_match.group(1)
            if number[0].isdigit():
                try:
                    if int(number.split('.')[0]) > 99:
                        content_buffer.append(line)
                        continue
                except ValueError:
                    pass
            flush_content()
            pending_number = number
            continue

        # 비볼드 조항 패턴 (폴백)
        plain_match = PLAIN_CLAUSE_RE.match(stripped)
        if plain_match:
            number = plain_match.group(1)
            title = plain_match.group(2).strip()
            if title and not title.isdigit():
                if number[0].isdigit():
                    try:
                        if int(number.split('.')[0]) > 99:
                            content_buffer.append(line)
                            continue
                    except ValueError:
                        pass
                register_clause(number, title)
                continue

        # NOTE 감지
        note_match = NOTE_RE.match(stripped)
        if note_match and current_clause:
            flush_content()
            current_note = note_match.group(1) or "1"
            initial_text = note_match.group(2).strip()
            if initial_text:
                content_buffer.append(initial_text)
            continue

        # EXAMPLE 감지
        example_match = EXAMPLE_RE.match(stripped)
        if example_match and current_clause:
            flush_content()
            current_example = example_match.group(1) or "1"
            initial_text = example_match.group(2).strip()
            if initial_text:
                content_buffer.append(initial_text)
            continue

        # 일반 내용 축적
        content_buffer.append(line)

    # 마지막 pending_number 처리
    if pending_number is not None:
        register_clause(pending_number, "(untitled)")

    # 마지막 버퍼 처리
    flush_content()

    # 결과 조립
    clause_list = []
    for num, clause in clauses.items():
        d = asdict(clause)
        clause_list.append(d)

    return {
        "document_title": document_title,
        "total_clauses": len(clause_list),
        "clauses": clause_list,
    }


def parse_file(md_path: str) -> dict:
    """파일을 읽고 파싱"""
    path = Path(md_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {md_path}")

    text = path.read_text(encoding='utf-8')
    result = parse_clauses(text)
    result["source_file"] = str(path.name)
    return result


def main():
    parser = argparse.ArgumentParser(
        description='ISO 문서 조항 구조 파싱'
    )
    parser.add_argument('md_file', help='파싱할 Markdown 파일 경로')
    parser.add_argument('-o', '--output', help='출력 JSON 파일 경로 (미지정 시 stdout)')
    parser.add_argument('--pretty', action='store_true', default=True,
                        help='JSON 포맷팅 (기본값: True)')

    args = parser.parse_args()

    try:
        result = parse_file(args.md_file)

        json_str = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json_str, encoding='utf-8')
            print(f"파싱 완료: {result['total_clauses']}개 조항 → {args.output}")
        else:
            print(json_str)

    except Exception as e:
        print(f"에러: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
