---
name: iso-toolkit
description: "ISO 표준 문서 비교 분석 도구. PDF 변환, 조항 파싱, 비교 보고서 생성, Excel 비교표 파싱, DIS 투표양식 작성 스크립트와 ISO 운송분야 멘탈모델 레퍼런스를 포함합니다. ISO 문서 검토, DIS/IS 버전 비교, 조항별 변경사항 분석, DIS 투표 의견 생성 시 사용하세요."
---

# ISO Toolkit

ISO 표준 문서의 버전 간 비교 분석을 위한 스크립트와 레퍼런스 모음.

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/clause_parser.py` | ISO MD 문서에서 조항 구조를 파싱 | `python clause_parser.py <md_file> -o <output.json>` |
| `scripts/diff_report.py` | 두 파싱 결과를 비교하여 MD 보고서 생성 | `python diff_report.py <is.json> <dis.json> -o <report.md>` |
| `scripts/excel_parser.py` | 전문가 비교표 Excel을 JSON으로 파싱 | `python excel_parser.py -i <excel> -s <sheet> -o <output.json>` |
| `scripts/ballot_writer.py` | DIS 투표양식 Word에 검토 의견 삽입 | `python ballot_writer.py -t <template.docx> -c <content.json> -o <output.docx>` |

## PDF 변환

ISO PDF → Markdown 변환에는 **intro-writer 플러그인의 MinerU 스크립트**를 재사용합니다.
MinerU가 설치되지 않은 환경에서는 **pymupdf4llm**을 대안으로 사용할 수 있습니다.

### 스크립트 탐색 순서

1. `intro-writer/skills/intro-toolkit/scripts/mineru_converter.py` (Glob으로 탐색)
2. `intro-writer/skills/intro-toolkit/scripts/md_postprocessor.py` (Glob으로 탐색)

MinerU 변환 후 md_postprocessor.py로 후처리하면 ISO 문서도 깔끔한 Markdown이 됩니다.

### 변환 명령

```bash
# MinerU 변환
python mineru_converter.py --mode single --input <pdf_path> --output <output_dir>

# 후처리
python md_postprocessor.py --input <md_dir> --output <processed_dir>

# pymupdf4llm 대안 (MinerU 미설치 시)
pip install pymupdf4llm
PYTHONIOENCODING=utf-8 python -c "
import pymupdf4llm, pathlib
md = pymupdf4llm.to_markdown('<pdf_path>')
pathlib.Path('<output.md>').write_text(md, encoding='utf-8')
"
```

## 조항 파싱

`clause_parser.py`는 ISO 문서의 조항 구조를 인식합니다:

- **pymupdf4llm 볼드 형식**: `## **5.1 Title**`, `## **3.1**` + `## **accuracy**`
- **일반 Markdown**: `## 5.1 Title`, `# Annex A`
- **부속서**: `## **Annex A**`, `# Annex B (informative)`
- **참고/비고**: `NOTE`, `EXAMPLE` 블록

### 파싱 출력 (JSON)

```json
{
  "document_title": "ISO 8178-1:2020",
  "total_clauses": 436,
  "clauses": [
    {
      "number": "5.1",
      "title": "Principle of emission measurement",
      "level": 2,
      "content": "The gaseous and particulate...",
      "notes": ["NOTE Monitoring and reviewing can include..."],
      "subclauses": ["5.1.1", "5.1.2"]
    }
  ]
}
```

## Excel 비교표 파싱

`excel_parser.py`는 전문가가 작성한 ISO 개정안 비교표를 파싱합니다:

- **병합 셀 처리**: openpyxl로 병합 영역 매핑, Column B non-None = 항목 경계
- **열 구조**: B(조항번호), C-H(IS 텍스트), I-N(DIS 텍스트), O-S(변경 유형)
- **변경 유형 정규화**: 한국어 → 영문 코드 (내용추가 → CONTENT_ADDED 등)

```bash
# 특정 시트 파싱
python excel_parser.py -i "비교표.xlsx" -s "8178-1" -o excel_parsed.json

# 전체 시트 파싱
python excel_parser.py -i "비교표.xlsx" -o excel_parsed_all.json
```

## 투표양식 작성

`ballot_writer.py`는 빈 DIS 투표양식(Word)에 검토 의견을 삽입합니다:

- **입력**: ballot_content.json (AI가 생성한 구조화된 검토 의견)
- **처리**: python-docx로 투표양식 열기 → 검토 의견 섹션 삽입 → 투표 선택 표시
- **글꼴**: 맑은 고딕 11pt

```bash
python ballot_writer.py -t "ISO-DIS_8178-1.docx" -c ballot_content.json -o ballot_filled.docx
```

## 비교 보고서

`diff_report.py`는 두 문서의 파싱 결과를 비교하여 Markdown 보고서를 생성합니다:

- **신설 조항** (Added): DIS에만 존재하는 조항
- **삭제 조항** (Removed): IS에만 존재하는 조항
- **수정 조항** (Modified): 양쪽 모두 존재하나 내용이 변경된 조항
- **번호 변경** (Renumbered): 조항 번호가 변경된 경우

## References

| File | Description |
|------|-------------|
| `references/iso-clause-patterns.json` | ISO 문서의 조항 번호 패턴, 표준 섹션 구조, 자동차 표준 키워드, 변경 중요도, DIS 투표 절차 |
| `references/iso-transport-mental-model.json` | ISO 운송/자동차 분야 멘탈모델. ISO 8178 시리즈 구조, 배출 규제 관계, 측정 기술 진화, 수소 엔진 과제, 교정 체계, DIS 투표 가이드, 한국 맥락 |

## 스크립트 호출 폴백 전략

```
Step 1: 상대 경로 시도
  python scripts/clause_parser.py ...

Step 2: Glob 폴백 (전체 플러그인 경로)
  Glob: **/iso-reviewer/skills/iso-toolkit/scripts/clause_parser.py

Step 3: 확장 Glob (파일명만)
  Glob: **/clause_parser.py

Step 4: 실패 시 즉시 에러 보고 — 절대 스크립트를 직접 작성하지 말 것
```

## 의존성

| Package | Purpose | Install |
|---------|---------|---------|
| openpyxl | Excel 파싱 (excel_parser.py) | `pip install openpyxl` |
| python-docx | Word 작성 (ballot_writer.py) | `pip install python-docx` |
| pymupdf4llm | PDF→MD 변환 (MinerU 대안) | `pip install pymupdf4llm` |
