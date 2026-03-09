---
name: intro-toolkit
description: "Toolkit resources for intro-writer including Marker PDF conversion scripts, MD post-processing, SCIE summary template, and linguistic patterns for Introduction analysis. Use when executing PDF conversion, style analysis, or Introduction writing workflows."
---

# Intro Toolkit

Use this skill for reusable resources needed by intro-writer agents.

- Run PDF conversion and post-processing scripts from `scripts/`.
- Load linguistic patterns and SCIE template from `references/`.
- Validate Introduction structure against linguistic pattern definitions.

## Resources

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/marker_converter.py` | Marker CLI wrapper for PDF→MD conversion (single/batch) |
| `scripts/md_postprocessor.py` | MD post-processing: section normalization, equation/table cleanup, section markers |

### References

| File | Purpose |
|------|---------|
| `references/linguistic-patterns.json` | Introduction-specific linguistic patterns: opening, gap, objective phrases, narrative flow, voice/tense |
| `references/scie-summary-template.md` | SCIE 9-section summary template for paper summarization |

## 스크립트 참조 및 실행 (CRITICAL)

스크립트는 이 스킬의 상대경로에 위치합니다:

```
scripts/marker_converter.py
scripts/md_postprocessor.py
```

**실행 순서:**

**Step 1. 상대경로로 실행** (최우선)

```bash
# PDF → MD 변환 (batch)
python scripts/marker_converter.py --input-dir [pdf_folder] --output-dir [md_output_folder]

# PDF → MD 변환 (single)
python scripts/marker_converter.py --single [pdf_file] --output-dir [md_output_folder]

# MD 후처리
python scripts/md_postprocessor.py --input-dir [md_folder] --output-dir [processed_output_folder]
```

**Step 2. 상대경로 실패 시 Glob 폴백**

```
Glob: **/intro-writer/skills/intro-toolkit/scripts/marker_converter.py
Glob: **/intro-writer/skills/intro-toolkit/scripts/md_postprocessor.py
```

**Step 3. Glob도 실패 시 확장 탐색**

```
Glob: **/marker_converter.py
Glob: **/md_postprocessor.py
```

**절대 금지**: 스크립트를 찾지 못했을 때 자체적으로 Python 코드를 작성하지 마세요.
반드시 에러를 보고하고 사용자에게 경로 확인을 요청하세요.

## Marker CLI 참조

### 설치

```bash
pip install marker-pdf
```

### 명령어

| 명령어 | 용도 |
|--------|------|
| `marker_single {pdf} --output_dir {dir} --output_format markdown` | 단일 PDF 변환 |
| `marker {folder} --output_dir {dir} --workers 4 --output_format markdown` | 폴더 일괄 변환 |

### Marker 출력 구조

Marker는 `{output_dir}/{stem}/{stem}.md` 구조로 출력합니다.
`marker_converter.py`가 이를 `{output_dir}/{stem}.md`로 자동 flatten 합니다.

## linguistic-patterns.json 구조

Introduction 분석 및 작성에 사용되는 언어 패턴:

| 카테고리 | 설명 |
|----------|------|
| `introduction_patterns.opening_phrases` | 문제 제기, 통계 시작, 중요성 진술 |
| `introduction_patterns.gap_identification` | 한계 지적, 갭 전환 |
| `introduction_patterns.objective_statement` | 목적 진술, 기여 미리보기 |
| `introduction_patterns.closing_patterns` | Introduction 마무리 패턴 |
| `narrative_flow.stages` | 5단계 서사 구조 (context → review → gap → solution → overview) |
| `voice_tense_patterns` | Active/Passive 비율, Present/Past 비율 |
| `transition_phrases` | 전환어 카테고리별 분류 |
| `hedging_expressions` | 헷징 표현 (may, could, suggest 등) |
| `citation_patterns` | 인용 형식 (numbered, author-year) |

## SCIE Summary Template

`references/scie-summary-template.md`는 9개 섹션으로 구성된 논문 요약 템플릿입니다:

1. Paper Information (서지 정보)
2. Research Background & Objective
3. Methodology
4. Key Results
5. Discussion & Contribution
6. Relevance to My Research
7. Key Figures & Tables
8. Notable Equations
9. Personal Notes
