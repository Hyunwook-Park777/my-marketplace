---
name: pdf-to-md
description: >
  MinerU 기반 범용 PDF→Markdown 변환 스킬. PDF 변환, PDF를 마크다운으로,
  문서 변환, 논문 변환, PDF 텍스트 추출을 요청할 때 사용하세요.
  텍스트/그림/수식/표를 손실 없이 변환하고, Obsidian 호환 출력을 생성합니다.
  PDF 대비 MD 완전성 검증(0~100점)을 포함합니다.
---

# PDF-to-MD Conversion Toolkit

MinerU 기반 범용 PDF→Markdown 변환 파이프라인.

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/mineru_converter.py` | MinerU CLI 래퍼. 단일/배치 PDF→MD 변환, Windows MAX_PATH 폴백, 출력 평탄화 |
| `scripts/md_postprocessor.py` | MD 후처리. 헤더 정리, HTML→MD 표 변환, 수식 정리, 아티팩트 제거, 이미지 경로 공백 처리 |
| `scripts/verify_figures.py` | 이미지 참조 검증 + MinerU 재변환 자동 복구 |
| `scripts/verify_conversion.py` | PDF vs MD 변환 품질 검증. 5개 카테고리별 0~100점 채점 |

## Script Resolution Protocol

스크립트 경로를 찾을 때 다음 3단계 폴백을 사용:
1. **상대 경로**: `skills/pdf-to-md/scripts/{script_name}`
2. **Glob 검색**: `**/scripts/{script_name}`
3. **확장 Glob**: `**/{script_name}`
4. 모든 검색 실패 시 → 에러 보고 (절대 스크립트를 직접 작성하지 않음)

## Quick Start

### 단일 PDF 변환
```bash
python scripts/mineru_converter.py --single ./document.pdf --output-dir ./output/
python scripts/md_postprocessor.py --single ./output/document.md --output ./output/document.md
python scripts/verify_conversion.py --pdf ./document.pdf --md ./output/document.md
```

### 배치 변환
```bash
python scripts/mineru_converter.py --input-dir ./pdfs/ --output-dir ./converted/
python scripts/md_postprocessor.py --input-dir ./converted/ --output-dir ./processed/
python scripts/verify_figures.py --md-dir ./processed/ --mode verify --check-images
python scripts/verify_conversion.py --pdf-dir ./pdfs/ --md-dir ./processed/ --output report.json
```

## MinerU CLI Reference

```bash
# 직접 호출 (Device Guard 가 차단하지 않는 환경)
mineru -p <input> -o <output> [-b backend] [-l language] [-m method] [-d device]

# 권장: Windows Device Guard / Application Control 로 `mineru.exe` 가 차단된 환경에서도 동작
python -m mineru.cli.client -p <input> -o <output> [-b backend] [-l language] [-m method] [-d device]
```

| Option | Values | Default |
|--------|--------|---------|
| `-b` backend | `pipeline`, `vlm-auto-engine`, `hybrid-auto-engine` | `pipeline` |
| `-l` language | `en`, `ko`, `ja`, `zh`, etc. | `en` |
| `-m` method | `auto`, `txt`, `ocr` | `auto` |
| `-d` device | `cpu`, `cuda`, `cuda:0`, `mps`, `npu` | auto-detect (cuda→cpu) |

### 실행 환경 노트
- `mineru_converter.py` 는 항상 `sys.executable -m mineru.cli.client` 형태로 MinerU 를 호출하므로 Windows Device Guard 가 `mineru.exe` 를 차단하는 환경에서도 안전하게 동작한다.
- `--device` 옵션을 생략하면 PyTorch `torch.cuda.is_available()` 로 GPU 를 자동 감지하고, 감지 실패 시 CPU 로 폴백한다.
- GPU 가속을 쓰려면 **CUDA 지원 PyTorch** 가 필요하다. 기본 `torch` 휠(CPU 전용)이 설치된 환경에서는 GPU 가 있어도 CPU 로 동작한다. 설치 예: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128` (CUDA 12.8).
- `verify_conversion.py` 와 `mineru_converter.py` 는 PyMuPDF 를 `pymupdf → fitz` 순서로 임포트하여, `fitz` shim DLL 이 정책에 의해 차단된 환경에서도 페이지 수/메타데이터 추출을 계속 수행한다.

## Post-processing Pipeline

`md_postprocessor.py`가 수행하는 처리:

1. **헤더 정리**: 선행 점(`.`) 제거, 번호 목록 헤더 수정
2. **수식 정리**: `$` 주변 공백 제거, `$$` 블록 수식 줄바꿈 보정
3. **표 변환**: HTML `<table>` → Markdown 표 (`|...|`) 변환
4. **아티팩트 제거**: 페이지 번호, 빈 링크, DOI/URL 라인 제거 (이미지 참조 보존)
5. **이미지 경로**: 공백 포함 경로를 CommonMark angle bracket (`<path>`)으로 감싸기

## Verification System

`verify_conversion.py`의 5개 카테고리 채점:

| Category | Weight | Metric |
|----------|--------|--------|
| Text completeness | 40% | MD/PDF word count ratio (≥0.85 = 100pts) |
| Image completeness | 25% | MD image refs / PDF image count |
| Table completeness | 15% | MD tables / PDF table indicators (estimated) |
| Equation completeness | 10% | MD equations / PDF equation indicators (estimated) |
| Structure quality | 10% | MD headings / PDF TOC entries |

**Verdict**: ≥85 "good" / 60~84 "acceptable" / <60 "poor"

**주의**: PDF의 표/수식 수는 휴리스틱 추정치이므로 `(estimated)` 라벨이 붙습니다.
스캔 PDF는 `get_text()` 결과가 빈약하여 자동 감지 후 경고합니다.

## Obsidian Compatibility

- **이미지**: 상대 경로 + angle bracket (`![](<path with spaces/img.jpg>)`)
- **수식**: `$inline$` + `$$block$$` 형식 유지
- **표**: Markdown pipe table 형식 (`| col1 | col2 |`)
- **헤딩**: `#`, `##`, `###` 표준 헤딩

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `MAX_PATH exceeded` | Windows 260자 제한 | 자동 short-path 폴백 적용 |
| `Conversion timed out` | 대용량 PDF | `--timeout` 값 증가 |
| `MinerU not installed` | mineru CLI 없음 | `pip install "mineru[all]"` |
| `pymupdf not installed` | fitz 없음 | `pip install pymupdf` (검증 기능용) |
