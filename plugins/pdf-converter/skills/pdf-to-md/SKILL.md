---
name: pdf-to-md
description: >
  MinerU 기반 PDF→Markdown 변환 스킬 (GPU 전용). 문서 언어에 따라 엔진을 자동 선택한다:
  한국어 문서는 MinerU 2.x + korean OCR, 영어 논문·보고서는 MinerU 4.x advanced 티어.
  PDF 변환, PDF를 마크다운/md로 바꿔줘, 옵시디언(Obsidian)에 넣게 변환, 논문 변환,
  보고서·공문·제안서 PDF 정리, PDF 텍스트·표·그림·수식 추출을 요청하면 파일 형식을
  명시하지 않아도 이 스킬을 사용하세요. 텍스트/그림/수식/표를 손실 없이 변환하고,
  PDF 대비 MD 완전성 검증(0~100점)을 포함합니다.
---

# PDF-to-MD Conversion Toolkit (v2.0)

MinerU 기반 PDF→Markdown 변환 파이프라인. 두 MinerU 엔진을 문서별로 골라 쓴다.

| Engine | 설치 위치 | 쓰는 문서 | 이유 |
|--------|----------|-----------|------|
| `mineru2` (MinerU 2.7.x, `pipeline` + 언어별 OCR) | 기본 Python | 한국어 문서, 스캔본 한국어 | `korean` OCR 모델로 이미지·스캔 영역 한글을 정확히 읽는다 |
| `mineru4` (MinerU 4.x, `--tier advanced`) | 별도 venv (`~/venvs/mineru4`) | 영어 논문·보고서 등 그 외 | 본문·화학식·% 표기가 더 정확하고 빠르며, 그래프 속 데이터와 이미지 속 글자도 추출한다 |

`--engine auto` (기본): PDF 텍스트 층을 문서 전체에서 최대 15쪽 샘플링해 한글 비율이 높으면 `mineru2`, 아니면 `mineru4`.
텍스트 층이 없는 스캔본은 `-l` 값을 따른다 (`-l ko` → `mineru2`). MinerU 4 venv 가 없으면 경고 후 전부 `mineru2`.

MinerU 4.x 의 OCR 은 3.4 이후 `ch` 모델로 통합되어 이미지/스캔 영역의 한글이 빠지거나 한자로 읽힌다 (2026-10 기준, 4.0.12 실측).
본문 텍스트 층이 있는 한국어 PDF 는 4.x 도 정상이지만, 손실 없는 변환이 목표라 한국어는 2.x 로 보낸다.

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/mineru_converter.py` | 진입점. 엔진 선택(`--engine`), 단일/배치 변환, Windows MAX_PATH 폴백, 출력 평탄화, Device Guard 안전 호출, GPU 강제 |
| `scripts/mineru4_converter.py` | MinerU 4.x 엔진. venv 탐색, `mineru-kit parse --format zip` 실행, zip → `{stem}.md` + `{stem}/images/` 정리 |
| `scripts/md_postprocessor.py` | MD 후처리. 헤더 정리, HTML→MD 표 변환, display 수식 보존, 아티팩트 제거, 이미지 경로 공백 처리, 이미지 분석 블록 추정값 표시 |
| `scripts/equation_fixer.py` | 수식 번호/화살표 복원. PDF 의 `(N.N.N)` 을 MD 의 display 수식과 짝지어 `\tag{N.N.N}` 삽입, 일부 화살표(`→`, stackrel 빈칸) 복원 |
| `scripts/verify_figures.py` | 이미지 참조 검증 + MinerU 재변환 자동 복구 |
| `scripts/verify_conversion.py` | PDF vs MD 변환 품질 검증. 5개 카테고리별 0~100점 채점 |

## Script Resolution Protocol

스크립트 경로를 찾을 때 다음 폴백 순서를 사용:
1. **상대 경로**: `skills/pdf-to-md/scripts/{script_name}`
2. **Glob 검색**: `**/pdf-to-md/scripts/{script_name}` (다른 플러그인의 같은 이름 스크립트와 혼동 방지)
3. 모든 검색 실패 시 → 에러 보고 (절대 스크립트를 직접 작성하지 않음)

## Quick Start

### 단일 PDF 변환
```bash
python scripts/mineru_converter.py --single ./document.pdf --output-dir ./output/
python scripts/md_postprocessor.py --single ./output/document.md --output ./output/document.md
python scripts/equation_fixer.py --pdf ./document.pdf --md ./output/document.md   # 선택
python scripts/verify_conversion.py --pdf ./document.pdf --md ./output/document.md
```

### 배치 변환 (같은 폴더에서 후처리 — 이미지 폴더가 MD 옆에 있어야 한다)
```bash
python scripts/mineru_converter.py --input-dir ./pdfs/ --output-dir ./converted/
python scripts/md_postprocessor.py --input-dir ./converted/ --output-dir ./converted/
python scripts/equation_fixer.py --pdf-dir ./pdfs/ --md-dir ./converted/ --report ./converted/equation_fix_report.json   # 선택
python scripts/verify_figures.py --md-dir ./converted/ --mode verify --check-images
# 이미지 누락 시: 최초 변환과 같은 옵션으로 재변환 (후처리·수식 복원 자동 재적용)
python scripts/verify_figures.py --md-dir ./converted/ --pdf-dir ./pdfs/ --mode repair --check-images --timeout 3600
python scripts/verify_conversion.py --pdf-dir ./pdfs/ --md-dir ./converted/ --output ./converted/verification_report.json
```

### 엔진/품질 지정
```bash
--engine mineru4 --tier standard     # 영어 대량 변환을 더 빠르게
--engine mineru2 -l korean           # 한국어 강제 (스캔본 등)
--engine mineru4 --pages 1-20        # 4.x 는 페이지 범위 지정 가능
```

## mineru_converter.py 옵션

| Option | Values | Default | 적용 엔진 |
|--------|--------|---------|-----------|
| `--engine` | `auto`, `mineru2`, `mineru4` | `auto` | – |
| `-l` language | `en`, `korean`, `japan`, `ch`, `latin` … (`ko`/`ja`/`zh` 자동 변환) | PDF 별 자동 감지 | mineru2 (auto 라우팅에도 사용) |
| `-b` backend | `pipeline`, `vlm-auto-engine`, `hybrid-auto-engine` | `pipeline` | mineru2 |
| `-m` method | `auto`, `txt`, `ocr` | `auto` | 둘 다 (4.x 는 `--ocr-mode`) |
| `-d` device | `cuda`, `cuda:0`, `cpu` | `cuda` | mineru2 |
| `--tier` | `flash`, `basic`, `standard`, `advanced` | `advanced` | mineru4 |
| `--pages` | `1-5,8`, `r3-r1`, `all` | 전체 | mineru4 |
| `--mineru4-python` | 4.x venv 의 python 경로 | `$MINERU4_PYTHON` → `~/venvs/mineru4` | mineru4 |
| `--timeout` | 초 (파일당) | 3600 | 둘 다 |
| `--allow-cpu` | – | 꺼짐 (GPU 전용) | 둘 다 |

`conversion_report.json` 의 각 파일 항목에 `engine` (예: `mineru2:pipeline:korean`, `mineru4:advanced`) 이 기록된다.

### 실행 환경 노트
- **GPU 전용**: CUDA 가 없으면 종료 코드 3 으로 중단한다. 2.x 는 기본 Python 의 `torch.cuda.is_available()`, 4.x 는 venv 의 torch 를 검사한다. CPU 가 필요하면 `--allow-cpu` 를 명시한다.
- **MinerU 2.x**: 항상 `python -m mineru.cli.client` 로 호출해 Device Guard 가 `mineru.exe` 를 막아도 동작한다. 백엔드/메서드별 결과 폴더(`{stem}/auto|txt|ocr|vlm|hybrid_auto/`)를 찾아 평탄화한다. Windows 에서 `hybrid-*`/`vlm-*` 는 `lmdeploy>=0.10.2,<0.12` 가 필요하며, 맞지 않으면 MinerU 가 종료 코드 0 으로 결과 없이 끝난다 (리포트 error 에 MinerU 오류 줄 기록).
- **MinerU 4.x**: 2.x 와 의존성이 충돌(lmdeploy 0.17 등)하므로 별도 venv 에 설치한다. `python -m mineru.kit.main parse` 로 호출하고, 짧은 임시 경로에서 해시 파일명으로 변환해 MAX_PATH/비ASCII 경로 문제를 피한다. 첫 실행은 모델 다운로드와 엔진 준비로 20분 이상 걸릴 수 있고, 이후에는 수 초 내 시작한다. VRAM 약 10GB 사용.
- **MinerU 4.x 설치 (Windows, CUDA 12.8 예)**:
  ```bash
  python -m venv %USERPROFILE%\venvs\mineru4
  %USERPROFILE%\venvs\mineru4\Scripts\python -m pip install torch==2.11.0 torchvision --index-url https://download.pytorch.org/whl/cu128
  %USERPROFILE%\venvs\mineru4\Scripts\python -m pip freeze | findstr /b torch > torch-constraints.txt
  %USERPROFILE%\venvs\mineru4\Scripts\python -m pip install "mineru[full]>=4.0,<5" -c torch-constraints.txt
  ```
- **이미지 경로**: 최종 이미지 경로가 260자를 넘으면 이미지 파일명을 `img_001.jpg` 처럼 줄이고 참조를 함께 고친다 (경고가 리포트에 남음).
- PyMuPDF 는 `pymupdf → fitz` 순서로 임포트하여 `fitz` shim DLL 이 정책에 막혀도 동작한다.

## Post-processing Pipeline

`md_postprocessor.py`가 수행하는 처리:

1. **헤더 정리**: 선행 점(`.`) 제거, 번호 목록 헤더 수정
2. **수식 정리**: `$$` 블록 수식 앞뒤 빈 줄 보정 (줄을 넘어 `$$` 를 짝짓지 않음)
3. **표 변환**: HTML `<table>` → Markdown 표 (`|...|`) 변환. 병합 셀(rowspan/colspan)이 있는 표는 칸 밀림을 막기 위해 HTML 그대로 유지 (Obsidian 에서 정상 렌더링)
4. **아티팩트 제거**: 숫자만 있는 줄(페이지 번호, 수식/코드/표 내부 제외), 빈 링크, 3회 이상 반복되는 DOI/URL 단독 줄(머리말·꼬리말)만 제거. DOI/URL 이 들어간 본문·참고문헌은 보존
5. **이미지 경로**: 공백 포함 경로를 CommonMark angle bracket (`<path>`)으로 감싸기
6. **이미지 분석 블록 표시** (MinerU 4.x): `<details><summary>scatter</summary>` 처럼 모델이 그래프/직인/그림에서 읽어낸 블록의 제목을 `MinerU 이미지 분석 (추정값): scatter` 로 바꾼다. 그래프에서 읽은 표(`~45` 등)는 모델 추정치이므로 원문 데이터로 인용하지 않는다.

## Verification System

`verify_conversion.py`의 5개 카테고리 채점:

| Category | Weight | Metric |
|----------|--------|--------|
| Text completeness | 40% | MD/PDF word count ratio (≥0.85 = 100pts) |
| Image completeness | 25% | 실제 존재하는 MD 이미지 파일 / PDF image count |
| Table completeness | 15% | MD tables (pipe + HTML, 이미지 분석 블록 제외) / PDF table indicators (estimated) |
| Equation completeness | 10% | MD equations / PDF equation indicators (estimated) |
| Structure quality | 10% | MD headings / PDF TOC entries |

**Verdict**: ≥85 "good" / 60~84 "acceptable" / <60 "poor"

**주의**: PDF의 표/수식 수는 휴리스틱 추정치이므로 `(estimated)` 라벨이 붙습니다. PDF 이미지 수는 로고처럼 반복되는 이미지도 세므로 공문 등에서는 이미지 점수가 낮게 나올 수 있습니다.
스캔 PDF는 `get_text()` 결과가 빈약하여 자동 감지 후 경고합니다.

## Obsidian Compatibility

- **이미지**: 상대 경로 + angle bracket (`![](<path with spaces/img.jpg>)`), 파일로 저장 (base64 내장 없음)
- **수식**: `$inline$` + `$$block$$` 형식 유지
- **표**: Markdown pipe table, 병합 셀 표는 HTML
- **헤딩**: `#`, `##`, `###` 표준 헤딩

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| exit 3 `CUDA GPU not available` | CPU 전용 torch 또는 GPU 없음 | CUDA PyTorch 설치, 꼭 필요하면 `--allow-cpu` |
| `MinerU 4.x unavailable` 경고 | 4.x venv 없음 | 위 설치 절차대로 venv 생성 또는 `--mineru4-python` 지정. 없으면 auto 는 2.x 로 진행 |
| `Output file not created (MinerU: ...)` | MinerU 가 모델 로드 등에 실패하고 종료 코드 0 반환 | 괄호 안 MinerU 오류 확인 (예: lmdeploy 버전) |
| `Image files renamed to img_NNN` 경고 | 출력 경로가 길어 MAX_PATH 초과 | 정상 동작. 짧은 출력 경로를 쓰면 원래 파일명 유지 |
| `Conversion timed out` | 대용량 PDF | `--timeout` 값 증가 |
| `MinerU 2.x is not installed` | 기본 Python 에 mineru 2.x 없음 | `pip install "mineru[all]<3"` |
| `pymupdf not installed` | PyMuPDF 없음 | `pip install pymupdf` (언어 감지·검증용) |
