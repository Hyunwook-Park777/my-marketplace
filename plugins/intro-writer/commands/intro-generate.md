# Intro Writer Orchestrator

참고 PDF 논문을 변환하고, 사용자 스타일을 분석한 후,
스타일이 반영된 Introduction을 작성하고, SCIE 요약을 생성하는
4단계 파이프라인 오케스트레이터입니다.

---

## 1. Overview

### 1.1 목적

- **입력**: 참고 PDF 논문 + 사용자 기존 논문 PDF + 연구 주제
- **출력**: Introduction.md + SCIE 요약 + 스타일 프로필

### 1.2 4 Phase 워크플로우

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Intro Writer Workflow                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  INPUT                                                              │
│  ├── ref_pdf_folder: 참고 논문 PDF 폴더                              │
│  ├── user_pdf_folder: 사용자 기존 논문 PDF 폴더                      │
│  ├── research_topic: 연구 주제                                       │
│  └── key_contributions: 핵심 기여점 (선택)                           │
│           ↓                                                         │
│  Phase 1: 참고 논문 PDF 변환 [pdf-converter agent]                   │
│  ├── Marker로 참고 PDF → MD 변환                                     │
│  ├── 후처리 정제 (수식, 표, 캡션 정리)                                │
│  └── → md_converted/                                                │
│           ↓                                                         │
│  Phase 2a: 사용자 논문 PDF 변환 [pdf-converter agent]                │
│  ├── 사용자 기존 논문 PDF → MD 변환                                   │
│  └── → user_md/                                                     │
│           ↓                                                         │
│  Phase 2b: 스타일 분석 [style-analyzer agent]                       │
│  ├── 사용자 논문 Introduction 스타일 분석                             │
│  └── → style_profile.json                                           │
│           ↓                                                         │
│  Phase 3: Introduction 작성 [intro-writer agent]                    │
│  ├── 참고 논문 내용 + 스타일 프로필 → Introduction.md                 │
│  └── → Introduction.md + intro_sources.json                         │
│           ↓                                                         │
│  Phase 4: SCIE 요약 생성 [paper-summarizer agent]                   │
│  ├── 참고 논문 MD별 SCIE 9-section 요약                              │
│  └── → md_summary/                                                  │
│           ↓                                                         │
│  OUTPUT                                                             │
│  ├── md_converted/          (변환된 참고 논문)                        │
│  ├── user_md/               (변환된 사용자 논문)                      │
│  ├── style_profile.json     (스타일 프로필)                           │
│  ├── Introduction.md        (완성된 Introduction)                    │
│  ├── intro_sources.json     (출처 매핑)                              │
│  └── md_summary/            (SCIE 요약)                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 사용자 입력 스키마

### 2.1 필수 입력

| 항목 | 설명 | 예시 |
|------|------|------|
| `ref_pdf_folder` | 참고 논문 PDF 폴더 | `./papers/reference/` |
| `user_pdf_folder` | 사용자 기존 논문 PDF 폴더 | `./papers/my-papers/` |
| `research_topic` | 작성할 논문의 연구 주제 | "Hydrogen dual-fuel engine knock characteristics" |

### 2.2 선택 입력

| 항목 | 설명 | 기본값 |
|------|------|--------|
| `output_dir` | 전체 출력 디렉토리 | `{CWD}/intro_output/` |
| `key_contributions` | 핵심 기여점 목록 | (빈 값) |
| `research_context` | 연구 맥락 (SCIE 요약의 Relevance 평가용) | (빈 값) |

---

## 3. Phase 1: 참고 논문 PDF 변환

### 3.1 pdf-converter 에이전트 호출

```
Task(subagent_type="intro-writer:pdf-converter")

프롬프트:
"다음 폴더의 PDF 논문들을 Markdown으로 변환해 주세요.

입력 폴더: {ref_pdf_folder}
출력 폴더: {output_dir}/md_converted/

모든 PDF를 변환하고 변환 결과를 보고해 주세요."

출력:
- {output_dir}/md_converted/*.md
- {output_dir}/md_converted/conversion_report.json
```

### 3.2 검증 기준

- [ ] 최소 1편 이상 변환 성공
- [ ] 각 논문에서 주요 섹션 식별 가능

---

## 4. Phase 2: 사용자 논문 변환 + 스타일 분석

### 4.1 Phase 2a: 사용자 논문 PDF 변환

```
Task(subagent_type="intro-writer:pdf-converter")

프롬프트:
"다음 폴더의 PDF 논문들을 Markdown으로 변환해 주세요.
이 논문들은 사용자 본인의 기존 논문입니다.

입력 폴더: {user_pdf_folder}
출력 폴더: {output_dir}/user_md/

모든 PDF를 변환하고 변환 결과를 보고해 주세요."

출력:
- {output_dir}/user_md/*.md
```

### 4.2 Phase 2b: 스타일 분석

```
Task(subagent_type="intro-writer:style-analyzer")

프롬프트:
"다음 폴더의 MD 논문들에서 Introduction 스타일을 분석해 주세요.
이 논문들은 사용자 본인이 작성한 논문입니다.

MD 폴더: {output_dir}/user_md/
출력 파일: {output_dir}/style_profile.json

깊은 분석(deep)으로 수행하고, 신뢰도 리포트도 생성해 주세요."

출력:
- {output_dir}/style_profile.json
- {output_dir}/style_confidence.md
```

### 4.3 검증 기준

- [ ] style_profile.json 생성됨
- [ ] 전체 신뢰도 ≥ 70%
- [ ] Introduction 관련 패턴 추출됨

---

## 5. Phase 3: Introduction 작성

### 5.1 intro-writer 에이전트 호출

```
Task(subagent_type="intro-writer:intro-writer")

프롬프트:
"다음 입력을 바탕으로 Introduction 섹션을 작성해 주세요.

참고 논문 MD: {output_dir}/md_converted/
스타일 프로필: {output_dir}/style_profile.json
연구 주제: {research_topic}
핵심 기여점: {key_contributions}

출력 파일:
- {output_dir}/Introduction.md
- {output_dir}/intro_sources.json

사용자의 스타일을 반영하여 작성하고,
모든 기술적 주장에 인용을 포함해 주세요."

출력:
- {output_dir}/Introduction.md
- {output_dir}/intro_sources.json
```

### 5.2 검증 기준

- [ ] Introduction.md 생성됨
- [ ] 서사 5단계 구조 확인
- [ ] intro_sources.json의 citation_ratio ≥ 0.70
- [ ] style_profile의 voice/tense 목표와 대략 일치

---

## 6. Phase 4: SCIE 요약 생성

### 6.1 paper-summarizer 에이전트 호출

```
Task(subagent_type="intro-writer:paper-summarizer")

프롬프트:
"다음 폴더의 변환된 MD 논문들에 대해 SCIE 9-section 요약을 생성해 주세요.

MD 폴더: {output_dir}/md_converted/
출력 폴더: {output_dir}/md_summary/
연구 맥락: {research_context}

각 논문별 요약과 전체 인덱스를 생성해 주세요."

출력:
- {output_dir}/md_summary/*_summary.md
- {output_dir}/md_summary/summary_index.md
```

---

## 7. 실행 프로토콜

### 7.1 시작 메시지

```
Intro Writer를 시작합니다.

이 도구는 참고 PDF 논문을 분석하고, 사용자의 논문 작성 스타일을 반영하여
Introduction 섹션을 자동 작성합니다.

다음 정보를 입력해 주세요:
1. 참고 논문 PDF 폴더 경로
2. 사용자 기존 논문 PDF 폴더 경로
3. 작성할 논문의 연구 주제
4. (선택) 핵심 기여점 목록
```

### 7.2 진행 상황 보고

각 Phase 완료 시 보고:

```
Phase 1 완료: 참고 논문 PDF 변환
   - 변환 성공: N편
   - 변환 실패: M편

Phase 2 진행 중: 사용자 스타일 분석
   - 사용자 논문 변환 완료: K편
   - 스타일 분석 중...
```

### 7.3 완료 메시지

```
Intro Writer 완료!

생성된 파일:
   {output_dir}/
   ├── md_converted/           (참고 논문 MD, N편)
   ├── user_md/                (사용자 논문 MD, K편)
   ├── style_profile.json      (스타일 프로필, 신뢰도: X%)
   ├── Introduction.md         (완성된 Introduction)
   ├── intro_sources.json      (출처 매핑, 인용률: Y%)
   └── md_summary/             (SCIE 요약, N편)

Introduction 통계:
   - 길이: W words / P paragraphs
   - Voice: Active X% / Passive Y%
   - 인용률: Z%
```

---

## 8. 에러 처리

### 8.1 참고 논문 변환 실패

```
참고 논문 PDF 변환 중 일부 파일 실패

실패 파일:
- paper_03.pdf: 스캔 이미지 PDF (OCR 필요)

권장 조치:
1. 스캔 PDF는 OCR 처리 후 재시도
2. 실패 파일을 제외하고 계속 진행

[계속 진행] / [중단]
```

### 8.2 사용자 논문 부족

```
사용자 논문이 부족합니다 (현재: N편, 권장: 3편 이상)

스타일 분석 신뢰도가 낮을 수 있습니다.

[낮은 신뢰도로 계속] / [추가 논문 제공] / [기본 스타일로 계속]
```

---

## 9. MUST NOT DO

- [ ] 직접 PDF 변환을 수행하지 않음 (pdf-converter에 위임 필수)
- [ ] 직접 스타일 분석을 수행하지 않음 (style-analyzer에 위임 필수)
- [ ] 직접 Introduction을 작성하지 않음 (intro-writer에 위임 필수)
- [ ] 직접 SCIE 요약을 생성하지 않음 (paper-summarizer에 위임 필수)
- [ ] Task(subagent_type=...) 없이 파이프라인 단계를 수행하지 않음

---

## 10. 메타데이터

```yaml
version: "1.0.0"
created: "2026-03-09"
category: "research"
workflow:
  - Phase 1: 참고 논문 PDF 변환 (Marker)
  - Phase 2a: 사용자 논문 PDF 변환 (Marker)
  - Phase 2b: Introduction 스타일 분석 (deep)
  - Phase 3: Introduction 작성 (스타일 반영)
  - Phase 4: SCIE 요약 생성 (9-section)
dependencies:
  - marker-pdf
output:
  - md_converted/
  - user_md/
  - style_profile.json
  - Introduction.md
  - intro_sources.json
  - md_summary/
```
