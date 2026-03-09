# Nature-Methods Paper Skills

Academic paper writing skill set based on style analysis of 14 Hydrogen ICE / Dual-Fuel Engine research papers.

## Overview

This plugin provides 9 specialized agents and 1 style guide skill for writing academic papers that follow the established writing patterns of combustion engine research papers published in top-tier journals (Energy, Energy Conversion and Management, SAE Technical Paper, etc.).

## Source Analysis

| Item | Detail |
|------|--------|
| Papers analyzed | 14 |
| Primary author | Hyunwook Park (KIMM) |
| Field | Hydrogen Internal Combustion Engine / Dual-Fuel Engine |
| Patterns extracted | 2,698 |
| Confidence score | 100% |

## Agents

| Agent | Purpose |
|-------|---------|
| `nature-methods-paper-orchestrator` | Full paper writing coordination |
| `nature-methods-title-writer` | Title generation (5 patterns) |
| `nature-methods-abstract-writer` | Abstract writing (5-part structure) |
| `nature-methods-introduction-writer` | Introduction writing (7-paragraph flow) |
| `nature-methods-methodology-writer` | Experimental setup / Methods |
| `nature-methods-results-writer` | Results and Discussion |
| `nature-methods-discussion-writer` | Separate Discussion (when needed) |
| `nature-methods-caption-writer` | Figure and Table captions |
| `nature-methods-verify` | Style compliance verification |

## Style Guide Skill

`nature-methods-style-guide` provides common reference materials:
- Voice and tense patterns by section
- High-frequency vocabulary (25 verbs, 25 transitions)
- Measurement format conventions
- Citation style rules (numbered brackets)
- Section-specific templates (6 sections)

## Key Style Characteristics

- **Citation**: Numbered brackets [1], [2,3], [4-6]
- **Voice**: 21.5% passive ratio (higher in Methods/Results)
- **Tense**: Past for findings; Present for facts and figure references
- **Person**: Third person; "this study" preferred over "we"
- **Avg sentence length**: 16.7 words
- **Top verbs**: increased, reduced, compared, indicated, achieved
- **Top transitions**: however, therefore, due to, according to
- **Conclusion format**: Numbered findings 1), 2), 3)...

---

## 한국어 설명

### 개요
이 플러그인은 수소 내연기관 / 이중연료 엔진 연구 논문 14편의 스타일을 분석하여 생성된 논문 작성 스킬 세트입니다.

### 사용 방법
1. Claude Code에서 `@nature-methods-paper-orchestrator`를 호출하여 전체 논문 작성을 시작합니다.
2. 또는 개별 섹션 작성자를 직접 호출할 수 있습니다:
   - `@nature-methods-abstract-writer` - 초록 작성
   - `@nature-methods-introduction-writer` - 서론 작성
   - `@nature-methods-methodology-writer` - 실험 방법 작성
   - `@nature-methods-results-writer` - 결과 및 토의 작성
3. 작성 완료 후 `@nature-methods-verify`로 스타일 준수 여부를 검증합니다.

### 분석 기반
- **분석 논문 수**: 14편
- **주 저자**: 박현욱 (한국기계연구원)
- **분야**: 수소 내연기관, 이중연료 엔진
- **게재 저널**: Energy, Energy Conversion and Management, SAE Technical Paper, Vienna Motor Symposium

### 주요 스타일 특징
- 번호 대괄호 인용: [1], [2,3], [4-6]
- 수동태 비율: 21.5% (Methods/Results에서 더 높음)
- 평균 문장 길이: 16.7 단어
- 결론 형식: 번호 매김 1), 2), 3)...
- 고빈도 동사: increased, reduced, compared, indicated, achieved
