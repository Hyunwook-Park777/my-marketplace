# journal-translator 변경 이력

## 2026-04-07: v1.0.0 → v1.1.0 (PDF 출력 + 초록 표 본문 변환)

### 배경
- 기존 Phase 4는 한국어 번역 MD → Word(.docx)만 생성
- 사용자가 PDF 출력도 요청
- Word/PDF 모두에서 초록이 5열 표로 렌더링되어 공간 낭비 및 레이아웃 깨짐 발생

### 변경 사항

#### 1. 신규 스크립트: `scripts/md_to_pdf_kr.py`
- **ReportLab 4.4.10** 기반 한국어 MD → PDF 변환기
- `md_to_docx_kr.py`와 동일한 구조 (CLI: `--input`/`--input-dir` 배치 모드)
- 핵심 기능:
  - 맑은 고딕 폰트 등록 (`C:/Windows/Fonts/malgun.ttf`, `malgunbd.ttf`)
  - MD 인라인 서식 → ReportLab HTML 태그 (`<b>`, `<i>`)
  - 이미지 삽입: 페이지 폭 맞춤, 극단 비율 처리, 페이지 높이 80% 제한
  - 표: `LongTable` (페이지 넘김 지원), 500자 초과 셀은 텍스트 폴백
  - Figure/Table 캡션 중앙 정렬, References 작은 폰트(9pt)
  - 블록인용(`>`) 지원
  - A4, 2.54cm 여백, 1.5 줄간격

#### 2. 초록 표 → 본문 변환 (`md_to_docx_kr.py` + `md_to_pdf_kr.py` 양쪽)
- **문제**: pymupdf4llm이 논문 초록을 아래 형태의 MD 표로 변환:
  ```
  |논문 정보<br>키워드:<br>수소 첨가<br>...|초 록||---|---|
  ||초록 본문 텍스트...|
  ```
  - `|---|---|`가 헤더 행과 같은 줄에 있어 5열 표로 파싱됨
  - 초록 텍스트가 5열 중 2번째에 위치 → 매우 좁은 열에 긴 텍스트 → 레이아웃 깨짐
- **해결**: 3개 함수 추가
  - `is_abstract_table(table_lines)` — 첫 줄에 `논문 정보`+`초 록` 패턴 감지
  - `parse_abstract_table(table_lines)` — `<br>` 기준 키워드 분리, 가장 긴 셀에서 초록 추출
  - `add_abstract_to_doc()` (DOCX) / `render_abstract_flowables()` (PDF) — 본문 형식 출력:
    - **키워드:** 수소 첨가, 연료 물성, ... (볼드 라벨 + 쉼표 구분)
    - **초록** (헤딩)
    - 초록 본문 (일반 단락)
- `flush_table()` 수정: 초록 표 감지 시 표 생성 대신 본문 렌더링 분기

#### 3. SKILL.md 수정
- Phase 4를 "4a. Word 변환" + "4b. PDF 변환"으로 분리
- `md_to_pdf_kr.py` CLI 사용법 및 Glob 경로 추가
- 출력 구조에 `_kr.pdf` 파일 추가
- 스크립트 참조 목록에 `md_to_pdf_kr.py` 추가

### 수정 파일 목록
| 파일 | 변경 유형 |
|------|----------|
| `scripts/md_to_pdf_kr.py` | 신규 (445줄) |
| `scripts/md_to_docx_kr.py` | 수정 (초록 표 감지/변환 함수 3개 추가) |
| `SKILL.md` | 수정 (Phase 4 확장, 스크립트 참조 추가) |

### 검증 결과 (JN-Korea 번역 파일 2편)

| 파일 | DOCX | PDF | 이미지 | 표 (변경 전→후) |
|------|------|-----|--------|----------------|
| H2 enriched NG in SI ICEs_kr | 4,343 KB | 5,685 KB | 60 | 10→4 (DOCX), 10→9 (PDF) |
| HCNG engine research in China_kr | 5,072 KB | 6,524 KB | 42 | 5→2 (DOCX), 5→4 (PDF) |

- 키워드: 본문 텍스트로 올바르게 출력 확인
- 초록: 헤딩 + 본문 단락으로 올바르게 출력 확인
- 이미지: 전체 삽입 확인
- 한국어 폰트(맑은 고딕): 적용 확인

### 기술 교훈

1. **ReportLab Table vs LongTable**: 일반 `Table`은 한 페이지에 모든 행이 들어가야 함.
   셀 내용이 페이지보다 크면 `too large on page` 에러 발생.
   → `LongTable` 사용하면 페이지 넘김 가능.

2. **500자 초과 셀 텍스트 폴백**: 초록처럼 셀 하나에 매우 긴 텍스트가 있으면
   LongTable도 한 셀이 페이지보다 클 때 실패. → 셀 최대 길이 검사 후
   Paragraph 텍스트로 폴백하여 페이지 넘침 방지.

3. **pymupdf4llm 초록 표 패턴**: 구분선(`|---|---|`)이 헤더와 같은 줄에 붙어 나옴.
   `parse_markdown_table()`이 이를 데이터 셀로 파싱 → 5열 표 생성.
   근본 원인은 PDF 레이아웃 분석의 한계이므로, 변환기 단에서 패턴 감지로 우회.

### 다음에 할 수 있는 작업
- plugin.json `version`을 `1.1.0`으로 업데이트
- marketplace.json 동기화
- 플러그인 캐시 3곳 동기화 (installed_plugins.json, marketplace cache, version cache)
- `md_to_pdf_kr.py`에 목차(Table of Contents) 자동 생성 추가 검토
