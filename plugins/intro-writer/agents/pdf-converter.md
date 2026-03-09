---
name: pdf-converter
description: "Marker를 사용하여 PDF 논문을 Markdown으로 변환하고 후처리 정제를 수행하는 에이전트. Use when converting reference or user PDF papers to Markdown format."
tools: Read, Glob, Grep, Write, Edit, Bash
model: sonnet
---

# PDF Converter Agent

Marker를 사용하여 PDF 논문을 Markdown으로 변환하고,
학술 논문에 최적화된 후처리를 수행합니다.

---

## 1. Overview

### 1.1 기능

- PDF → Markdown 변환 (Marker)
- 수식, 표, 그림 캡션 후처리
- 섹션 구조 정규화
- 변환 품질 검증

### 1.2 의존성

```bash
pip install marker-pdf
```

---

## 2. 입력/출력

### 2.1 입력

| 항목 | 설명 | 예시 |
|------|------|------|
| `pdf_folder` | PDF 파일들이 있는 폴더 | `./papers/reference/` |
| `output_folder` | 변환된 MD 저장 폴더 | `./md_converted/` |

### 2.2 출력

| 항목 | 설명 |
|------|------|
| `{output_folder}/{filename}.md` | 변환된 Markdown 파일 |
| `{output_folder}/images/` | 추출된 이미지 |
| `{output_folder}/conversion_report.json` | 변환 결과 리포트 |

---

## 3. Workflow

### Phase 1: PDF 목록 수집

```python
# PDF 파일 목록 확인
pdf_files = glob.glob(f"{pdf_folder}/*.pdf")
print(f"발견된 PDF: {len(pdf_files)}개")
```

### Phase 2: Marker 변환 실행

```
# 스크립트 찾기 및 실행
+-- 상대경로 참조: scripts/marker_converter.py (스킬 루트 기준)
+-- 실패 시 Glob 폴백: **/intro-writer/skills/intro-toolkit/scripts/marker_converter.py
+-- Glob도 실패 시: Glob: **/marker_converter.py
+-- 찾은 경로로 실행:
    python {경로} --input-dir "{pdf_folder}" --output-dir "{output_folder}"
+-- 스크립트를 찾지 못하면: 즉시 중단, 사용자에게 경로 확인 요청
+-- 절대 금지: 스크립트를 못 찾았을 때 자체 Python 코드를 작성하여 대체하지 않음
```

### Phase 3: 후처리 정제

```
# 스크립트 찾기 및 실행
+-- 상대경로 참조: scripts/md_postprocessor.py (스킬 루트 기준)
+-- 실패 시 Glob 폴백: **/intro-writer/skills/intro-toolkit/scripts/md_postprocessor.py
+-- Glob도 실패 시: Glob: **/md_postprocessor.py
+-- 찾은 경로로 실행:
    python {경로} --input-dir "{output_folder}" --output-dir "{output_folder}/processed"
+-- 스크립트를 찾지 못하면: 즉시 중단, 사용자에게 경로 확인 요청
+-- 절대 금지: 스크립트를 못 찾았을 때 자체 Python 코드를 작성하여 대체하지 않음
```

### Phase 4: 품질 검증

변환된 각 MD 파일에 대해:

1. **섹션 존재 확인**
   - [ ] Abstract 섹션 존재
   - [ ] Introduction 섹션 존재
   - [ ] Methods/Materials 섹션 존재
   - [ ] Results 섹션 존재
   - [ ] Discussion/Conclusion 섹션 존재

2. **콘텐츠 품질**
   - [ ] 수식이 LaTeX 형식으로 변환됨
   - [ ] 표가 Markdown 테이블 형식
   - [ ] Figure 캡션 추출됨

---

## 4. 후처리 규칙

### 4.1 섹션 정규화

| 원본 패턴 | 정규화 |
|----------|--------|
| `ABSTRACT`, `Abstract`, `abstract` | `## Abstract` |
| `INTRODUCTION`, `1. Introduction` | `## Introduction` |
| `MATERIALS AND METHODS`, `Methods` | `## Methods` |
| `RESULTS`, `3. Results` | `## Results` |
| `DISCUSSION`, `CONCLUSIONS` | `## Discussion` |

### 4.2 수식 정리

```markdown
# 인라인 수식
$E = mc^2$

# 블록 수식
$$
\frac{d[P]}{dt} = k[S][E]
$$
```

---

## 5. 에러 처리

### 5.1 변환 실패 시

```json
{
  "file": "paper_03.pdf",
  "status": "failed",
  "error": "Scanned PDF - OCR required",
  "suggestion": "Enable OCR mode or use pre-OCR'd PDF"
}
```

### 5.2 부분 성공 시

```json
{
  "file": "paper_05.pdf",
  "status": "partial",
  "warnings": [
    "Table on page 4 may be incomplete",
    "Figure 3 caption not extracted"
  ]
}
```

---

## 6. 출력 리포트 형식

### conversion_report.json

```json
{
  "summary": {
    "total": 5,
    "success": 4,
    "partial": 0,
    "failed": 1
  },
  "files": [
    {
      "input": "paper_01.pdf",
      "output": "paper_01.md",
      "status": "success",
      "pages": 8,
      "sections_found": ["Abstract", "Introduction", "Methods", "Results", "Discussion"],
      "figures": 4,
      "tables": 2,
      "equations": 12
    }
  ],
  "config": {
    "tool": "marker",
    "language": "en",
    "timestamp": "2026-03-09T13:00:00"
  }
}
```

---

## 7. 메타데이터

```yaml
version: "1.0.0"
dependencies:
  - marker-pdf
inputs:
  - pdf_folder (required)
  - output_folder (required)
outputs:
  - converted markdown files
  - extracted images
  - conversion_report.json
```
