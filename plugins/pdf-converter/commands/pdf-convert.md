---
name: pdf-convert
description: >
  PDF를 Markdown으로 변환합니다. MinerU 기반 4-Phase 파이프라인으로
  변환, 후처리, 이미지 검증, 품질 검증을 수행합니다.
user_invocable: true
---

# PDF to Markdown Conversion

PDF 문서를 Markdown으로 변환하는 4-Phase 파이프라인 오케스트레이터.

## User Input Schema

사용자에게 다음 정보를 확인합니다:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `pdf_input` | Yes | - | PDF 폴더 또는 단일 파일 경로 |
| `output_dir` | No | `{CWD}/md_output/` | 출력 디렉토리 |
| `language` | No | `en` | OCR 언어 (en, ko, ja, zh 등) |
| `verify` | No | `true` | 품질 검증 활성화 여부 |

## Execution Flow

### Step 0: 환경 확인

1. MinerU 설치 확인: `mineru --version`
2. PyMuPDF 설치 확인 (검증용): `python -c "import fitz"`
3. 입력 경로 존재 확인
4. 출력 디렉토리 생성

### Step 1: PDF → Markdown 변환 (Phase 1)

`pdf-converter` 에이전트의 Phase 1을 실행합니다.

**단일 파일:**
```
Agent: pdf-converter → Phase 1 (single mode)
Input: pdf_input (file path)
Output: output_dir/{stem}.md
```

**폴더:**
```
Agent: pdf-converter → Phase 1 (batch mode)
Input: pdf_input (directory path)
Output: output_dir/*.md
```

`conversion_report.json`을 확인하여 변환 결과를 보고합니다.

### Step 2: Markdown 후처리 (Phase 2)

변환된 MD 파일을 정리합니다:
- 헤더 정규화
- HTML 표 → Markdown 표
- 수식 정리
- 아티팩트 제거
- 이미지 경로 공백 처리

### Step 2.5: 수식 번호 / 화살표 복원 (Phase 2.5)

`equation_fixer.py`를 실행하여 MinerU 가 드롭한 `(N.N.N)` 식 번호와 누락된 화학
반응 화살표(`→`, `⇌`)를 복원합니다. 원본 PDF 가 있어야만 수행되는 선택 단계.

```
Agent: pdf-converter → Phase 2.5 (단일 파일 또는 배치)
Input: pdf_path + md_path  (또는 pdf_dir + md_dir)
Output: MD 에 \tag{N.N.N} 삽입 + 화살표 적극 복원
```

화살표 복원은 **매칭되지 않은 수식을 포함한 모든 display 수식**에서 실행되며,
PDF 의 placeholder 패턴을 분석해 **단방향 / 양방향을 자동 구분**한다:
  - `\stackrel{X}{ }` → `\xrightarrow{X}` (중첩 중괄호 X 지원)
  - `\stackrel{ }{X}` → `\xrightarrow[X]{}`
  - 수식 본문의 2-space 연속 공백 →
    - PDF 원문에 `±±`, `«±`, `^`, `⇌` 이 나타나면 → `\rightleftharpoons`
    - PDF 원문에 `->`, `-*`, `→`, `S` 이 나타나면 → `\rightarrow`
    - PDF 증거가 없으면 (미매칭 수식 포함) → `\rightarrow` (안전 기본값)
  - LaTeX 명시 spacing `\quad`, `\,` 등 인접부는 스킵

참고:
- 번호 매칭은 식 본문의 **canonicalised signature** + 선행 문단 유사도의
  하이브리드 점수로 이루어지며, 문서 순서(monotone)를 유지한다.
- PyMuPDF 가 `→` / `⇌` 유니코드를 다양한 Latin-1 문자로 왜곡 추출하므로
  placeholder 패턴 사전을 기반으로 복원. 확신 없는 경우 `\rightarrow` 를 기본값으로 하고
  사용자가 필요 시 `\rightleftharpoons` 로 교정한다.

### Step 3: 이미지 검증 + 수리 (Phase 3)

1. `verify` 모드로 이미지 참조 검증
2. 누락 파일 발견 시 → `repair` 모드로 MinerU 재변환

### Step 4: 변환 품질 검증 (Phase 4)

`verify` 옵션이 `true`인 경우:

1. PDF 원본과 변환된 MD를 비교
2. 5개 카테고리별 점수 산출
3. `verification_report.json` 생성
4. 결과 요약 보고

## Output Summary

실행 완료 시 다음을 보고합니다:

```
=== PDF→MD 변환 완료 ===

변환 결과:
  - 총 파일: N개
  - 성공: N개
  - 실패: N개

품질 검증 (verify=true):
  - 평균 점수: XX.X/100
  - Good (≥85): N개
  - Acceptable (60-84): N개
  - Poor (<60): N개

출력 위치: {output_dir}/
리포트: {output_dir}/verification_report.json
```

## Error Handling

| Error | Action |
|-------|--------|
| MinerU 미설치 | `pip install "mineru[all]"` 안내 후 중단 |
| PyMuPDF 미설치 | 경고 후 Phase 4 스킵 (변환은 정상 진행) |
| PDF 경로 없음 | 에러 메시지 출력 후 중단 |
| 변환 타임아웃 | `--timeout` 증가 안내 |
| 전체 실패 | `conversion_report.json` 확인 안내 |
