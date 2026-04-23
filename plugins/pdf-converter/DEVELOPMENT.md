# PDF-to-MD Converter Plugin 개발 기록

## 개요

- **플러그인명**: pdf-converter
- **버전**: 1.0.0
- **생성일**: 2026-04-12
- **위치**: `my-marketplace/plugins/pdf-converter/`

기존 intro-writer, journal-translator, iso-reviewer 세 플러그인이 각각 PDF→MD 변환 코드를 중복 보유하고 있어, 범용 독립 플러그인으로 분리하여 재사용성을 확보하고, PDF 원본 vs MD 비교 **변환 품질 검증** 기능을 신규 개발하였다.

### 핵심 요구사항

1. MinerU 기반 PDF→MD 변환
2. 수백 페이지 PDF도 내용 생략 없이 변환
3. 텍스트, 그림, 수식, 표 모두 빠짐없이 변환
4. Obsidian 호환 표준 MD 출력 (이미지 경로 등)
5. PDF 원본과 변환 MD를 비교대조하는 품질 검증

---

## 플러그인 구조

```
pdf-converter/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   └── pdf-converter.md          ← 4-Phase 파이프라인 에이전트
├── commands/
│   └── pdf-convert.md            ← 오케스트레이터 커맨드
├── skills/
│   └── pdf-to-md/
│       ├── SKILL.md              ← 스킬 정의
│       └── scripts/
│           ├── mineru_converter.py    ← intro-writer에서 복사+범용화
│           ├── md_postprocessor.py    ← intro-writer에서 복사+범용화
│           ├── verify_figures.py      ← intro-writer에서 복사+범용화
│           └── verify_conversion.py   ← 신규 개발 (핵심)
├── AGENTS.md
└── DEVELOPMENT.md                ← 이 파일
```

**총 10개 파일** (기존 복사+범용화 3 + 신규 7)

---

## 구현 단계별 기록

### Step 1: 플러그인 스캐폴딩

`.claude-plugin/plugin.json` 생성.

```json
{
  "name": "pdf-converter",
  "version": "1.0.0",
  "author": { "name": "Baekdong Cha", "email": "orientpine@gmail.com" },
  "license": "MIT"
}
```

### Step 2: mineru_converter.py 복사 + 범용화

**소스**: `intro-writer/skills/intro-toolkit/scripts/mineru_converter.py` (684줄)

| 항목 | 기존 (intro-writer) | 변경 |
|------|---------------------|------|
| `extract_sections()` | 7개 학술논문 섹션만 감지 | 모든 `#`, `##`, `###` 헤딩 추출 |
| 페이지 수 | `len(content)//3000` 추정 | PyMuPDF `fitz` 실제 페이지 수 추출 (`get_pdf_page_count()` 신규) |
| 타임아웃 | 하드코딩 3600s | `--timeout` CLI 파라미터 (기본 3600s) |
| 학술논문 경고 | `< 3 files` 또는 `>= 13 files` 경고 | 제거 (범용이므로 파일 수 제한 불필요) |
| `min_papers` 파라미터 | 기본 3, CLI 노출 | 제거 |
| docstring | "Convert PDF papers" | "Convert PDF documents" |

**유지한 기능**: Windows MAX_PATH 핸들링, 배치 모드, short-path 폴백, 출력 폴더 평탄화, 이미지 참조 업데이트, conversion_report.json 생성

### Step 3: md_postprocessor.py 복사 + 범용화

**소스**: `intro-writer/skills/intro-toolkit/scripts/md_postprocessor.py` (410줄)

| 항목 | 기존 | 변경 |
|------|------|------|
| `normalize_section_headers()` | 학술 섹션으로 정규화 (Abstract→`## Abstract` 등 9개 매핑) | 선행 점(`.`) 제거 + 번호목록 헤더 수정만 수행. 학술 정규화 매핑 전체 제거 |
| `extract_figure_captions()` | "Figure N" 패턴 강제 포맷 (`**Figure N.**`) | 함수 자체 제거 (범용 문서에서는 불필요) |
| `add_section_markers()` | 기본 활성화 | 기본 비활성화 (`--markers` 옵션으로만 활성화) |
| `process_markdown()` | `add_markers=True` 기본값 | `add_markers=False` 기본값 |
| `process_file()` | `add_markers=True` 기본값 | `add_markers=False` 기본값 |
| CLI | `--input-dir` + `--output-dir` (배치만) | `--single <file>` 단일 파일 모드 추가, `--output` 단일 출력 경로 |
| CLI 플래그 | `--no-markers` (비활성화) | `--markers` (활성화) — 기본이 꺼짐으로 바뀜 |
| sections 추출 | `re.findall(r'## (\w+)', ...)` | `re.findall(r'^##\s+(.+)$', ..., re.MULTILINE)` — 모든 ## 헤딩 |

**유지한 기능**: 수식 정리, HTML→MD 표 변환, 아티팩트 제거 (negative lookbehind), 이미지 경로 공백 처리 (angle brackets)

### Step 4: verify_figures.py 복사 + 범용화

**소스**: `intro-writer/skills/intro-toolkit/scripts/verify_figures.py` (351줄)

- `repair_missing_figures()`의 `script_dir` 참조가 같은 `scripts/` 디렉토리 기준으로 동작 (cross-plugin 참조 없음)
- 나머지 로직은 동일하게 유지

### Step 5: verify_conversion.py 신규 개발 (핵심)

PDF 원본과 변환된 MD를 비교하여 변환 품질을 검증하는 스크립트.

**의존성**: `pymupdf` (fitz)

#### 3개 핵심 함수

**`extract_pdf_metadata(pdf_path) → dict`**

PyMuPDF로 PDF에서 추출:
- `page_count`: 실제 페이지 수
- `total_words`: 전체 단어 수 (`page.get_text()` 합산)
- `image_count`: 임베디드 이미지 수 (`page.get_images()` 합산)
- `table_indicators`: "Table N" / "Tab. N" 캡션 패턴 카운트
- `equation_indicators`: "(N)" 수식 번호 패턴 카운트
- `has_toc` / `toc_entries`: TOC 존재 여부 및 항목 수
- `is_scanned`: 스캔 PDF 자동 감지 (페이지당 단어 < 10)

**`extract_md_metadata(md_path) → dict`**

MD 파일에서 추출:
- `total_words`: 단어 수 (이미지/수식/HTML 태그 제거 후)
- `heading_count`: 헤딩 수
- `image_refs`: `![` 패턴 수
- `image_files_found`: 실제 존재하는 이미지 파일 수
- `table_count`: MD 표 구분선(`|---|`) 수
- `inline_eq_count`: `$...$` 수
- `block_eq_count`: `$$...$$` 수

**`compare_pdf_md(pdf_meta, md_meta) → dict`**

5개 카테고리별 점수 산출 (가중 합산 → 0~100점):

| 카테고리 | 가중치 | 기준 |
|----------|--------|------|
| 텍스트 완전성 | 40% | MD/PDF 단어 수 비율 (≥0.85=100, 0.70~0.85=70~100 선형, <0.50=10) |
| 이미지 완전성 | 25% | MD 이미지 참조/PDF 이미지 수 비율 |
| 표 완전성 | 15% | MD 표/PDF 표 추정치 비율 |
| 수식 완전성 | 10% | MD 수식/PDF 수식 추정치 비율 |
| 구조 품질 | 10% | MD 헤딩/PDF TOC 항목 비율 |

**판정**: ≥85 "good" / 60~84 "acceptable" / <60 "poor"

**설계 고려사항**:
- PDF 헤더/푸터/페이지번호는 MD에서 제거되므로 단어 비율 85%를 100점 기준으로 설정
- PDF 표/수식 수는 휴리스틱 추정치 → `(estimated)` 라벨 표기
- 스캔 PDF는 `get_text()` 결과가 빈약 → 자동 감지 후 "scanned PDF detected" 경고 + OCR 모드 추천
- 기대값 0인 카테고리는 100점 (해당 없음 처리)

### Step 6: SKILL.md / Agent / Command / AGENTS.md 작성

- **SKILL.md**: 4개 스크립트 테이블, 3단계 스크립트 해석 프로토콜, Quick Start, MinerU CLI 레퍼런스, 검증 시스템 설명, Obsidian 호환성, 에러 처리
- **pdf-converter.md (agent)**: 4-Phase 파이프라인 (변환→후처리→이미지검증→품질검증)
- **pdf-convert.md (command)**: 사용자 입력 스키마 (pdf_input, output_dir, language, verify), Step 0~4 실행 흐름
- **AGENTS.md**: 에이전트 카탈로그

### Step 7: marketplace.json 업데이트

`my-marketplace/.claude-plugin/marketplace.json`의 `plugins` 배열에 pdf-converter 항목 추가.

### Step 8: 플러그인 등록 + 캐시 동기화

3개 위치에 동기화 수행:

| 위치 | 경로 |
|------|------|
| marketplace 캐시 | `~/.claude/plugins/marketplaces/my-marketplace/plugins/pdf-converter/` |
| version 캐시 | `~/.claude/plugins/cache/my-marketplace/pdf-converter/1.0.0/` |
| marketplace.json | `~/.claude/plugins/marketplaces/my-marketplace/.claude-plugin/marketplace.json` |

레지스트리 2개 업데이트:

| 파일 | 키 |
|------|-----|
| `installed_plugins.json` | `pdf-converter@my-marketplace` → installPath, version 1.0.0 |
| `settings.json` | `enabledPlugins` → `"pdf-converter@my-marketplace": true` |

---

## 검증 결과

| 항목 | 결과 |
|------|------|
| `plugin.json` JSON 유효성 | OK |
| `marketplace.json` JSON 유효성 | OK |
| `mineru_converter.py` 구문 검사 | OK |
| `md_postprocessor.py` 구문 검사 | OK |
| `verify_figures.py` 구문 검사 | OK |
| `verify_conversion.py` 구문 검사 | OK |
| LF 줄바꿈 (.md 파일) | OK |
| `installed_plugins.json` 등록 | OK |
| `settings.json` 활성화 | OK |
| marketplace 캐시 동기화 | OK |
| version 캐시 동기화 | OK |

---

## 수정 대상 파일 최종 목록

| # | 파일 | 작업 |
|---|------|------|
| 1 | `.claude-plugin/plugin.json` | 신규 |
| 2 | `agents/pdf-converter.md` | 신규 |
| 3 | `commands/pdf-convert.md` | 신규 |
| 4 | `skills/pdf-to-md/SKILL.md` | 신규 |
| 5 | `skills/pdf-to-md/scripts/mineru_converter.py` | 복사+범용화 |
| 6 | `skills/pdf-to-md/scripts/md_postprocessor.py` | 복사+범용화 |
| 7 | `skills/pdf-to-md/scripts/verify_figures.py` | 복사+범용화 |
| 8 | `skills/pdf-to-md/scripts/verify_conversion.py` | **신규 개발** |
| 9 | `AGENTS.md` | 신규 |
| 10 | `../../.claude-plugin/marketplace.json` | 수정 (pdf-converter 항목 추가) |

---

## 향후 검증 방법

1. **MinerU 설치 확인**: `mineru --version`
2. **단일 PDF 변환 테스트**:
   ```bash
   python scripts/mineru_converter.py --single <pdf> --output-dir ./test_output/
   python scripts/md_postprocessor.py --input-dir ./test_output/ --output-dir ./test_output/
   python scripts/verify_figures.py --md-dir ./test_output/ --mode verify --check-images
   python scripts/verify_conversion.py --pdf <pdf> --md ./test_output/<stem>.md
   ```
3. **Obsidian 확인**: 변환된 MD를 Obsidian에서 열어 이미지/표/수식 렌더링 확인
4. **대용량 테스트**: 100+ 페이지 PDF로 타임아웃 없이 완료되는지 확인
5. **검증 점수 확인**: `verification_report.json`의 `overall_score`가 합리적인지 확인
6. **플러그인 로딩 확인**: Claude Code 재시작 후 스킬/에이전트 정상 로드 확인
