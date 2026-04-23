---
name: pdf-converter
description: >
  MinerU 기반 범용 PDF→Markdown 변환 에이전트. 4-Phase 파이프라인으로
  PDF 변환, MD 후처리, 이미지 검증/수리, 변환 품질 검증을 수행합니다.
tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Edit
---

# PDF Converter Agent

MinerU 기반 4-Phase PDF→Markdown 변환 파이프라인을 실행하는 에이전트.

## Pipeline

### Phase 1: PDF → Markdown 변환

`mineru_converter.py`를 사용하여 PDF를 Markdown으로 변환합니다.

**단일 파일:**
```bash
python {scripts}/mineru_converter.py --single "{pdf_path}" --output-dir "{output_dir}" -l {language} --timeout {timeout}
```

**배치 모드:**
```bash
python {scripts}/mineru_converter.py --input-dir "{pdf_dir}" --output-dir "{output_dir}" -l {language} --timeout {timeout}
```

**GPU 강제 / CPU 강제:**
```bash
python {scripts}/mineru_converter.py --single "{pdf_path}" --output-dir "{output_dir}" --device cuda   # GPU 강제
python {scripts}/mineru_converter.py --single "{pdf_path}" --output-dir "{output_dir}" --device cpu    # CPU 강제
```

**출력**: `{output_dir}/{stem}.md` + `{output_dir}/{stem}/images/`

**실행 환경 노트:**
- 스크립트는 항상 `python -m mineru.cli.client` 로 MinerU 를 호출하므로, Windows Device Guard / Application Control 이 `mineru.exe` 를 차단하는 환경에서도 안전하게 동작한다.
- `--device` 생략 시 PyTorch `torch.cuda.is_available()` 로 GPU 를 자동 감지하고 실패 시 CPU 로 폴백한다. GPU 활용을 위해서는 **CUDA 빌드 PyTorch** 가 필요하다(기본 `torch` 휠은 CPU 전용).
- 실패 파일은 Windows MAX_PATH 문제일 수 있음 → 자동 short-path 폴백 적용됨
- `conversion_report.json`에서 성공/실패 확인

### Phase 2: Markdown 후처리

`md_postprocessor.py`를 사용하여 변환된 MD를 정리합니다.

**배치 모드:**
```bash
python {scripts}/md_postprocessor.py --input-dir "{output_dir}" --output-dir "{output_dir}"
```

**단일 파일:**
```bash
python {scripts}/md_postprocessor.py --single "{md_path}" --output "{md_path}"
```

**처리 내용:**
1. 헤더 앞 점(`.`) 제거
2. 번호 목록 → 적절한 헤딩 레벨로 수정
3. HTML `<table>` → Markdown 표 변환
4. 수식 주변 공백/줄바꿈 정리
5. 페이지 번호, 빈 링크 등 아티팩트 제거
6. 공백 포함 이미지 경로를 angle bracket으로 감싸기

### Phase 2.5: 수식 번호/화살표 복원 (선택)

`equation_fixer.py`를 사용하여 MinerU 가 누락한 `(N.N.N)` 식 번호와 화학 반응
화살표를 복원합니다. 원본 PDF 가 있을 때만 수행하며, PDF 에서 식 번호와 그 직전
수식 본문을 추출해 MD 의 display 수식과 **본문 시그니처 + 선행 문단 유사도** 로
짝지은 뒤 `\tag{N.N.N}` 을 삽입합니다.

화살표 복원은 **모든 display 수식**에 적용되며 (매칭되지 않은 수식 포함), 다음 세
패턴을 모두 처리합니다:

1. `\stackrel{X}{ }` → `\xrightarrow{X}`  (중첩 중괄호 X 지원)
2. `\stackrel{ }{X}` → `\xrightarrow[X]{}`
3. 수식 본문 중간의 2-space 연속 공백 → `\rightarrow`
   (LaTeX 명시 spacing `\quad`, `\,` 등 인접부는 건너뜀, 끝점 인접부도 제외)

PyMuPDF 가 PDF 의 `→` / `⇌` 유니코드를 `±±`, `«±`, `-*`, `^`, `S`, `->` 등
다양한 Latin-1 placeholder 로 잘못 추출합니다. 스크립트는 이 **placeholder
패턴 사전** 을 사용하여 PDF 의 `(N.N.N)` 라벨 주변에서 실제 화살표 방향을 복원합니다:

- **단방향 placeholder** (`->`, `-*`, `→`, 또는 chemistry 토큰으로 둘러싼 ` S `)
  → `\rightarrow`
- **양방향 placeholder** (`±±`, `«±`, `«»`, `⇌`, 또는 chemistry 토큰으로 둘러싼 ` ^ `)
  → `\rightleftharpoons`

매칭된 수식은 해당 PDF 라벨의 arrow_type 을 그대로 반영한다. 매칭되지 않은 수식은
PDF 측 증거가 없으므로 `\rightarrow` 를 안전한 기본값으로 사용한다 (가역 반응은
필요 시 수동으로 `\rightleftharpoons` 로 교정).

**단일 파일:**
```bash
python {scripts}/equation_fixer.py --pdf "{pdf_path}" --md "{md_path}"
```

**배치:**
```bash
python {scripts}/equation_fixer.py --pdf-dir "{pdf_dir}" --md-dir "{output_dir}" --report "{output_dir}/equation_fix_report.json"
```

**옵션:**
- `--threshold 0.40` – 매칭 커트라인 (기본 0.55, 낮추면 매칭 수↑ 정확도↓)
- `--no-arrows` – 화살표 복원 끄기 (숫자 태그만 추가)

매칭은 보수적이라 모든 수식에 태그가 붙지는 않는다. 특히 짧은 심볼 전용 수식은 매칭이
어려울 수 있으므로 `report.json` 의 `unmatched` 리스트를 확인하여 필요 시 수동 보정한다.

### Phase 3: 이미지 검증 + 수리

`verify_figures.py`를 사용하여 이미지 참조를 검증합니다.

```bash
python {scripts}/verify_figures.py --md-dir "{output_dir}" --mode verify --check-images
```

**이미지 누락 파일이 있으면 repair 모드 실행:**
```bash
python {scripts}/verify_figures.py --md-dir "{output_dir}" --pdf-dir "{pdf_dir}" --mode repair --check-images
```

### Phase 4: 변환 품질 검증

`verify_conversion.py`를 사용하여 PDF 대비 MD 완전성을 검증합니다.

**배치 모드:**
```bash
python {scripts}/verify_conversion.py --pdf-dir "{pdf_dir}" --md-dir "{output_dir}" --output "{output_dir}/verification_report.json"
```

**단일 파일:**
```bash
python {scripts}/verify_conversion.py --pdf "{pdf_path}" --md "{md_path}"
```

**출력**: `verification_report.json`
- 5개 카테고리별 점수 (텍스트 40%, 이미지 25%, 표 15%, 수식 10%, 구조 10%)
- 종합 점수 0~100점
- 판정: good (≥85) / acceptable (60~84) / poor (<60)

## Script Resolution

스크립트 경로 `{scripts}`를 찾을 때:
1. `skills/pdf-to-md/scripts/` 디렉토리를 Glob으로 검색
2. 실패 시 `**/scripts/{script_name}`으로 확장 검색
3. **절대 스크립트를 직접 작성하지 않음** — 검색 실패 시 에러 보고

## Requirements

- MinerU: `pip install "mineru[all]"`
- PyMuPDF (Phase 4용): `pip install pymupdf`
