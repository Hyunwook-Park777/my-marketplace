---
name: journal-translator
description: >
  국제 학술 저널(PDF)을 한국어로 전문 번역하는 5-Phase 파이프라인 스킬.
  PDF → Markdown 변환, 그림/그래프 보존, 변환 품질 교차 검증, 기계공학 전문가 수준
  영한 번역, 이미지 포함 Word 문서 생성을 수행합니다.
  사용자가 논문 번역, PDF 번역, 저널 한국어 변환, 학술 자료 번역 등을 요청할 때
  이 스킬을 사용하세요. 영어 논문을 한국어로 옮기거나 기술 문서를 번역할 때도
  적극 활용하세요.
---

# Journal Translator — 국제 저널 한국어 번역 파이프라인

영문 학술 논문 PDF를 기계공학 전문가 수준의 한국어로 번역하여 Word 문서로 출력하는
5단계 파이프라인입니다.

## 사전 준비

### 필수 패키지
```
pip install "mineru[all]" python-docx Pillow
```

### 입력 요구사항
- 입력: PDF 파일이 있는 폴더 경로 (또는 단일 PDF)
- 출력: 같은 폴더 내 `translated_output/` 하위 디렉토리에 생성

## Pipeline Overview

```
Phase 1: PDF → Markdown (pymupdf4llm 또는 MinerU)
Phase 2: Markdown 후처리 + 교차 검증
Phase 3: 영→한 전문 번역 (섹션별)
Phase 4: 한국어 Markdown → Word (.docx) + 이미지 삽입
Phase 5: 최종 품질 검증
```

---

## Phase 1: PDF → Markdown 변환

PDF를 Markdown으로 변환하며 그림, 그래프, 표, 수식을 최대한 보존합니다.
두 가지 변환기를 지원하며, 환경에 맞게 선택합니다.

### 방법 A: pymupdf4llm (권장 — 추가 모델 다운로드 불필요)

이 스킬의 `scripts/pdf_to_md.py`를 사용합니다.
파일명에 공백/특수문자가 있어도 자동으로 짧은 임시 경로에서 변환 후 결과를 이동합니다.

```bash
python <scripts/pdf_to_md.py 경로> --input-dir <PDF_폴더> --output-dir <PDF_폴더>/md_converted/
```

단일 파일:
```bash
python <scripts/pdf_to_md.py 경로> --single <PDF파일> --output-dir <PDF_폴더>/md_converted/
```

스크립트 탐색: Glob `**/journal-translator/scripts/pdf_to_md.py`

### 방법 B: MinerU (고품질 레이아웃 분석 — 모델 필요)

MinerU는 딥러닝 레이아웃 모델을 사용하여 더 정확한 구조 분석이 가능하지만,
모델 다운로드(~2GB)가 필요하고 Windows에서 AppLocker 정책에 의해
`mineru.exe` 실행이 차단될 수 있습니다.

**MinerU 실행 방법** (exe 차단 우회):
```bash
python -m magic_pdf.tools.cli -p <PDF_폴더> -o <PDF_폴더>/md_converted/ -m auto
```

**MinerU 모델 미설치 시**:
```bash
pip install huggingface_hub
python -c "from huggingface_hub import snapshot_download; snapshot_download('opendatalab/PDF-Extract-Kit-1.0', local_dir='C:/Users/hwpar/models')"
```

**MinerU 설정 파일** (`~/magic-pdf.json`) 필요 — 없으면 자동 생성해야 합니다.

또는 intro-writer의 `mineru_converter.py`를 사용:
```bash
python <mineru_converter.py 경로> --input-dir <PDF_폴더> --output-dir <PDF_폴더>/md_converted/
```

### Phase 1 완료 조건
- 각 PDF에 대응하는 `.md` 파일 생성
- `conversion_report.json`에서 status가 "success"
- 이미지 폴더(`{stem}/images/`)가 존재하고 이미지 파일이 있을 것

---

## Phase 2: Markdown 후처리 + 교차 검증

### 2a. 후처리
`md_postprocessor.py`로 변환된 MD를 정리합니다:
- 헤더 정규화
- HTML 표 → Markdown 표 변환
- 수식 정리
- 이미지 경로 공백 처리

```bash
python <md_postprocessor.py 경로> --input-dir <PDF_폴더>/md_converted/ --output-dir <PDF_폴더>/md_processed/
```

### 2b. 교차 검증
`verify_figures.py`로 이미지 참조 무결성을 확인합니다:

```bash
python <verify_figures.py 경로> --md-dir <PDF_폴더>/md_processed/ --check-images --mode verify
```

검증 항목:
- [ ] 각 MD 파일에 이미지 참조(`![...]`)가 존재하는가
- [ ] 참조된 이미지 파일이 실제로 디스크에 있는가
- [ ] 원본 PDF의 주요 섹션(Abstract, Introduction 등)이 MD에 존재하는가
- [ ] 표(Table)가 올바르게 변환되었는가

이미지 누락 시 `--mode repair`로 자동 복구:
```bash
python <verify_figures.py 경로> --md-dir <PDF_폴더>/md_processed/ --pdf-dir <PDF_폴더> --mode repair --check-images
```

### 이미지 폴더 복사
md_processed 폴더에는 MD 파일만 복사되므로, 이미지 폴더를 수동으로 복사해야 합니다:
```bash
# md_converted/ 안의 이미지 폴더들을 md_processed/로 복사
cp -r <PDF_폴더>/md_converted/*/images <PDF_폴더>/md_processed/
# 또는 논문별 폴더 전체:
for d in <PDF_폴더>/md_converted/*/; do
  stem=$(basename "$d")
  cp -r "$d" "<PDF_폴더>/md_processed/$stem"
done
```

---

## Phase 3: 영→한 전문 번역

이 단계가 스킬의 핵심입니다. 각 MD 파일을 섹션별로 나누어 번역합니다.

### 번역 페르소나

당신은 **기계공학 박사 학위를 보유하고 10년 이상 내연기관/연소/터보차저/수소엔진
분야에서 연구한 시니어 엔지니어**입니다. 아래 원칙을 따릅니다:

### 번역 원칙

1. **전문 용어는 한국어 관용 표현을 우선** 사용하되, 최초 등장 시 영문 병기
   - brake thermal efficiency → 제동 열효율(brake thermal efficiency)
   - turbocharger → 터보차저
   - exhaust gas recirculation → 배기가스 재순환(EGR)
   - pre-ignition → 조기점화(pre-ignition)
   - knock → 노킹
   - lean burn → 희박연소
   - stoichiometric → 양론비(stoichiometric)
   - port fuel injection → 포트 분사(PFI)
   - direct injection → 직접 분사(DI)

2. **기술 약어는 번역하지 않고 원문 유지**
   - BMEP, BSFC, BTE, EGR, PFI, DI, TWC, VGT, WGT 등
   - 단, 최초 등장 시 한국어 풀네임 병기

3. **수치와 단위는 원문 그대로 유지**
   - "at 1200 rpm" → "1200 rpm에서"
   - "increased by 15%" → "15% 증가하였다"

4. **수식은 번역하지 않음** — `$...$`, `$$...$$` 블록은 그대로 유지

5. **Figure/Table 캡션 번역**
   - "Figure 3. Effect of..." → "**그림 3.** ...의 영향"
   - "Table 2. Comparison..." → "**표 2.** ...의 비교"

6. **References 섹션은 번역하지 않음** — 원문 그대로 유지

7. **문체**: 학술 논문의 경어체 사용
   - "~하였다", "~이다", "~을 나타낸다"
   - 수동태보다 능동태 선호: "was observed" → "관찰되었다" (O) / "관찰하였다" (O)

8. **이미지 참조는 번역하되 마크다운 문법 유지**
   - `![](path/to/image.jpg)` 구문은 그대로 유지
   - 본문의 "as shown in Fig. 3" → "그림 3에 나타낸 바와 같이"

### 번역 절차

각 MD 파일에 대해:

1. **파일 읽기**: MD 파일 전체를 읽는다
2. **섹션 분할**: `## ` 헤더를 기준으로 섹션을 나눈다
3. **섹션별 번역**: 각 섹션을 위의 원칙에 따라 번역한다
   - Abstract → 초록
   - Introduction → 서론
   - Methods / Experimental → 실험 방법
   - Results → 결과
   - Discussion → 고찰
   - Conclusion → 결론
   - References → References (번역하지 않음)
4. **번역된 MD 저장**: `<PDF_폴더>/translated/` 디렉토리에 `{원본이름}_kr.md`로 저장

### 번역 품질 자가 점검

번역 완료 후 아래를 확인:
- [ ] 전문 용어의 일관성 (같은 용어를 문서 전체에서 동일하게 번역)
- [ ] 수식/수치가 원문과 동일한가
- [ ] 이미지 참조(`![...]`)가 깨지지 않았는가
- [ ] Figure/Table 번호가 원문과 일치하는가
- [ ] References가 원문 그대로 유지되었는가

---

## Phase 4: 한국어 MD → Word (.docx) + PDF 변환

번역된 한국어 MD 파일을 이미지 포함 Word 문서와 PDF로 변환합니다.

### 4a. Word 변환

`scripts/md_to_docx_kr.py` 스크립트를 사용합니다:

```bash
python <scripts/md_to_docx_kr.py 경로> --input <translated/논문_kr.md> --output <translated_output/논문_kr.docx> --image-base <md_processed 또는 md_converted 폴더>
```

배치 모드:
```bash
python <scripts/md_to_docx_kr.py 경로> --input-dir <translated/> --output-dir <translated_output/> --image-base <md_processed/>
```

### 4b. PDF 변환

`scripts/md_to_pdf_kr.py` 스크립트를 사용합니다 (ReportLab 기반):

```bash
python <scripts/md_to_pdf_kr.py 경로> --input <translated/논문_kr.md> --output <translated_output/논문_kr.pdf> --image-base <md_processed 또는 md_converted 폴더>
```

배치 모드:
```bash
python <scripts/md_to_pdf_kr.py 경로> --input-dir <translated/> --output-dir <translated_output/> --image-base <md_processed/>
```

스크립트 탐색: Glob `**/journal-translator/scripts/md_to_pdf_kr.py`

### 문서 스펙 (Word / PDF 공통)
- **본문 폰트**: 맑은 고딕 11pt (한국어), Times New Roman 11pt (영문/수식)
- **제목 폰트**: 맑은 고딕 Bold
- **줄간격**: 1.5
- **페이지**: A4, 여백 2.54cm
- **이미지**: 원본 크기 기준 페이지 폭에 맞춤 (최대 16cm)
- **표**: Markdown 표 → Word/PDF 표로 변환
- **Figure 캡션**: 이미지 아래 중앙 정렬

---

## Phase 5: 최종 품질 검증

생성된 Word 파일의 품질을 확인합니다:

- [ ] Word 파일이 정상 생성되었는가 (파일 크기 > 10KB)
- [ ] 이미지가 Word에 삽입되었는가
- [ ] 한국어 폰트가 올바르게 적용되었는가
- [ ] 목차 구조(헤더)가 원문과 일치하는가
- [ ] 번역 품질 샘플 확인 (Abstract, Conclusion 부분)

### 출력 구조
```
<PDF_폴더>/
├── 원본1.pdf
├── 원본2.pdf
├── md_converted/          ← Phase 1 출력
│   ├── 원본1.md
│   ├── 원본1/images/
│   ├── 원본2.md
│   └── 원본2/images/
├── md_processed/          ← Phase 2 출력
│   ├── 원본1.md
│   └── 원본2.md
├── translated/            ← Phase 3 출력
│   ├── 원본1_kr.md
│   └── 원본2_kr.md
└── translated_output/     ← Phase 4 최종 출력
    ├── 원본1_kr.docx
    ├── 원본1_kr.pdf
    ├── 원본2_kr.docx
    └── 원본2_kr.pdf
```

---

## 스크립트 참조

이 스킬은 두 곳의 스크립트를 사용합니다:

### journal-translator 전용 (Phase 1, Phase 4)
경로: 이 스킬의 `scripts/` 디렉토리
- `pdf_to_md.py` — PDF→MD 변환 (pymupdf4llm, 공백/특수문자 파일명 자동 처리)
- `md_to_docx_kr.py` — 한국어 MD→Word 변환 (이미지 포함)
- `md_to_pdf_kr.py` — 한국어 MD→PDF 변환 (ReportLab, 이미지 포함)

### intro-writer 플러그인 재활용 (Phase 1B, Phase 2)
경로: `my-marketplace/plugins/intro-writer/skills/intro-toolkit/scripts/`
- `mineru_converter.py` — PDF→MD 변환 (MinerU 백엔드, 모델 필요)
- `md_postprocessor.py` — MD 후처리 (헤더 정규화, HTML 표 변환 등)
- `verify_figures.py` — 이미지 검증/복구
