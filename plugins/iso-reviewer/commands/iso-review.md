---
name: iso-review
description: "ISO 표준 문서의 IS 버전과 DIS 버전을 비교 분석하는 6-Phase 파이프라인 오케스트레이터. PDF 변환, 조항 비교, Excel 교차 검증, AI 심층 분석, 보고서 검증, Ballot 투표양식 생성까지 전 과정을 수행합니다."
---

# ISO Review Pipeline

ISO 표준 문서의 IS(기존) 버전과 DIS(신규) 버전을 비교하여
조항별 변경사항 분석 보고서를 생성하고, 선택적으로 전문가 비교표 교차 검증 및
DIS 투표양식 자동 생성까지 수행하는 파이프라인.

## 입력 스키마

### 필수

| 필드 | 설명 | 예시 |
|------|------|------|
| `is_pdf` | 기존 IS 버전 PDF 경로 | `"C:/docs/ISO_8178-1_2020.pdf"` |
| `dis_pdf` | 신규 DIS 버전 PDF 경로 | `"C:/docs/ISO_DIS_8178-1.pdf"` |
| `standard_name` | ISO 표준 이름 | `"ISO 8178-1"` |

### 선택

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `output_dir` | `{CWD}/iso_review_output/` | 결과 저장 폴더 |
| `focus_areas` | `[]` | 특별히 주목할 조항 번호 목록 |
| `excel_path` | (없음) | 전문가 비교표 Excel 경로 (Phase 3용) |
| `excel_sheet` | (없음) | Excel 시트 이름 (부분 매칭). 미지정 시 전체 시트 |
| `ballot_templates` | (없음) | 투표양식 .docx 파일/폴더 경로 (Phase 6용) |
| `reviewer_name` | (없음) | 검토자 이름 |
| `reviewer_org` | (없음) | 검토자 소속 |

## 출력 구조

```
{output_dir}/
├── md_converted/              # Phase 1: 원본 변환
│   ├── is_document.md
│   └── dis_document.md
├── md_processed/              # Phase 1: 후처리된 MD
│   ├── is_document.md
│   └── dis_document.md
├── is_parsed.json             # Phase 2: IS 조항 파싱 결과
├── dis_parsed.json            # Phase 2: DIS 조항 파싱 결과
├── comparison.json            # Phase 2: 비교 결과 JSON
├── diff_report.md             # Phase 2: 기계적 비교 보고서
├── excel_parsed.json          # Phase 3: Excel 파싱 결과 (선택)
├── excel_crossref.json        # Phase 3: 교차 검증 결과 (선택)
├── analysis_report.md         # Phase 4+5: AI 심층 분석 보고서
├── ballot_content.json        # Phase 6: 검토 의견 JSON (선택)
└── ballot_{standard_name}.docx # Phase 6: 완성된 투표양식 (선택)
```

## 파이프라인 실행

### Phase 1: PDF → Markdown 변환

두 PDF를 각각 Markdown으로 변환합니다.

```
Task(subagent_type="iso-reviewer:pdf-converter")

프롬프트: "다음 ISO PDF 문서를 Markdown으로 변환해 주세요.
입력: {is_pdf}
출력 폴더: {output_dir}/md_converted/
변환 후 {output_dir}/md_processed/ 폴더에 후처리 결과도 저장해 주세요."
```

IS와 DIS 두 문서를 순차적으로 변환합니다.
변환 후 md_processed/ 폴더에 두 파일이 있는지 확인합니다.

**파일명 규칙**: 변환된 파일명이 길 경우, 후속 단계에서 쉽게 식별하도록
IS 문서는 `is_{standard_name}.md`, DIS 문서는 `dis_{standard_name}.md`로 복사합니다.

**MinerU 대안**: MinerU가 설치되지 않은 환경에서는 pymupdf4llm을 대안으로 사용할 수 있습니다:
```bash
pip install pymupdf4llm
PYTHONIOENCODING=utf-8 python -c "
import pymupdf4llm, pathlib
md = pymupdf4llm.to_markdown('{pdf_path}')
pathlib.Path('{output_path}').write_text(md, encoding='utf-8')
"
```

### Phase 2: 조항 파싱 + 기계적 비교

변환된 두 Markdown을 조항별로 비교합니다.

```
Task(subagent_type="iso-reviewer:clause-comparator")

프롬프트: "다음 두 ISO 문서를 조항별로 비교 분석해 주세요.
IS 버전: {output_dir}/md_processed/{is_filename}
DIS 버전: {output_dir}/md_processed/{dis_filename}
출력 폴더: {output_dir}/
표준 이름: {standard_name}
주목 조항: {focus_areas}"
```

이 단계에서 생성되는 파일:
- `is_parsed.json`, `dis_parsed.json` — 조항 파싱 결과
- `comparison.json` — 기계적 비교 결과
- `diff_report.md` — 기계적 비교 보고서

### Phase 3: Excel 비교표 교차 검증 (선택)

> **조건**: `excel_path`가 제공된 경우에만 실행. 미제공 시 Phase 4로 스킵.

#### 3.1 Excel 파싱

excel_parser.py를 Glob으로 탐색하여 실행합니다:

```
Glob: **/iso-reviewer/skills/iso-toolkit/scripts/excel_parser.py
```

```bash
PYTHONIOENCODING=utf-8 python {excel_parser_path} \
    --input "{excel_path}" \
    --sheet "{excel_sheet}" \
    -o "{output_dir}/excel_parsed.json"
```

#### 3.2 교차 검증

clause-comparator에게 교차 검증을 요청합니다:

```
Task(subagent_type="iso-reviewer:clause-comparator")

프롬프트: "기존 비교 결과에 대해 Excel 교차 검증을 수행해 주세요.
comparison.json: {output_dir}/comparison.json
excel_parsed.json: {output_dir}/excel_parsed.json
출력 폴더: {output_dir}/
analysis_report.md에 §8 교차 검증 결과 섹션을 추가해 주세요."
```

또는, Phase 2의 clause-comparator 호출 시 `excel_parsed_path`를 함께 전달하여 한 번에 처리할 수 있습니다.

### Phase 4: AI 심층 분석 + 멘탈모델

Phase 2에서 기계적 비교만 수행한 경우, 이 단계에서 AI 심층 분석을 수행합니다.
Phase 2의 clause-comparator가 이미 분석 보고서를 생성한 경우, 이 단계에서는 멘탈모델을 활용한 보강만 수행합니다.

clause-comparator는 다음 레퍼런스를 자동 로드합니다:
- `iso-clause-patterns.json` — 표준 구조, 변경 중요도 기준
- `iso-transport-mental-model.json` — 도메인 전문 지식 (있는 경우)

분석 보고서는 최대 9개 섹션 (§1-§7 기본 + §8 교차 검증 + §9 도메인 컨텍스트)으로 구성됩니다.

### Phase 5: 보고서 검증 및 보강

최종 analysis_report.md를 읽고 품질을 검증합니다:

1. **파싱 커버리지 확인**
   - md_processed의 원본 MD에서 주요 조항 번호를 Grep으로 검색
   - 파싱 결과와 대조하여 누락된 조항이 있는지 확인
   - 누락 조항이 있으면 analysis_report.md에 주의사항으로 추가

2. **보고서 완성도 확인**
   - 기본 7개 섹션이 모두 있는지 확인
   - 핵심 변경사항 요약이 구체적인지 확인
   - 실무 대응 권고사항이 있는지 확인
   - Excel 교차 검증 수행 시 §8 섹션이 있는지 확인
   - 멘탈모델 참조 시 §9 섹션이 있는지 확인

3. **교차 검증 불일치 보강** (excel_crossref.json 있는 경우)
   - EXCEL_ONLY 항목이 있으면 해당 조항을 수동 재검토
   - TYPE_MISMATCH 항목의 원인을 분석하여 보고서에 추가

### Phase 6: Ballot Form 자동 생성 (선택)

> **조건**: `ballot_templates`가 제공된 경우에만 실행. 미제공 시 스킵.

ballot-writer 에이전트를 호출하여 투표양식을 완성합니다:

```
Task(subagent_type="iso-reviewer:ballot-writer")

프롬프트: "다음 분석 결과를 바탕으로 투표양식을 작성해 주세요.
분석 보고서: {output_dir}/analysis_report.md
비교 데이터: {output_dir}/comparison.json
교차 검증: {output_dir}/excel_crossref.json (있는 경우)
투표양식 템플릿: {ballot_templates}
표준 이름: {standard_name}
출력 폴더: {output_dir}/
검토자: {reviewer_name}
소속: {reviewer_org}"
```

이 단계에서 생성되는 파일:
- `ballot_content.json` — 구조화된 검토 의견
- `ballot_{standard_name}.docx` — 완성된 투표양식

### 최종 결과 보고

모든 Phase 완료 후 사용자에게 결과를 보고합니다:

```
## 분석 완료

### 결과 파일
- 분석 보고서: {output_dir}/analysis_report.md
- 기계적 비교: {output_dir}/diff_report.md
- 비교 데이터: {output_dir}/comparison.json
- Excel 교차 검증: {output_dir}/excel_crossref.json (Phase 3 실행 시)
- 투표양식: {output_dir}/ballot_{standard_name}.docx (Phase 6 실행 시)

### 변경 통계
- 신설: N개 조항
- 삭제: N개 조항
- 수정: N개 조항
- 번호변경: N개 조항
- 변경없음: N개 조항
```

## 에러 처리

| Phase | 에러 | 대응 |
|-------|------|------|
| 1 | MinerU/pymupdf4llm 미설치 | 설치 안내 후 중단 |
| 1 | PDF 변환 실패 | 에러 메시지와 함께 해당 파일 건너뛰기 |
| 2 | 파싱 조항 수 0 | MD 파일 직접 확인, clause_parser.py 패턴 문제 확인 |
| 2 | 비교 결과 비정상 | comparison.json 검토 후 수동 보정 |
| 3 | Excel 파싱 실패 | 에러 보고, Phase 4로 진행 (Excel 없이) |
| 3 | 교차 검증 매칭률 극저 | Excel 시트 선택 확인, 조항 번호 형식 차이 확인 |
| 4 | 멘탈모델 미발견 | iso-clause-patterns.json만으로 분석 진행 |
| 5 | 보고서 불완전 | 누락 섹션 보완 |
| 6 | ballot_writer.py 실패 | ballot_content.json만 생성, Word 파일은 수동 작성 안내 |

## 특수 사례

### IATF 16949
- ISO 9001 본문과 IATF 추가 요구사항이 혼재
- IATF 요구사항은 보통 박스/별도 서체로 표시됨
- 이를 구분하여 분석할 수 있도록 clause-comparator에 안내

### 부속서가 많은 표준
- ISO 19880 시리즈처럼 부속서가 본문만큼 중요한 경우
- 부속서도 동등하게 비교 대상에 포함

### 다국어 표준
- ISO 원문은 영어/프랑스어 병기가 기본
- 파싱은 영어 기준으로 수행, 프랑스어 부분은 무시

### 복수 Part 동시 분석 (ISO 8178-1,4,5)
- 각 Part를 개별 실행하여 분석
- Excel이 여러 시트에 걸친 경우 `--sheet` 옵션으로 Part별 파싱
- 결과를 종합하여 시리즈 전체 관점의 의견 작성 가능
