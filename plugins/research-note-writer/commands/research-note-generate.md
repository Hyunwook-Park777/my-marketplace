---
description: 참여연구원 로스터·양식·근거자료로 다개년 연구노트(통합 .docx)를 자동 생성하는 오케스트레이터
---

# /research-note-generate

`research-note-toolkit` 스킬을 사용해 다개년 연구노트 통합본을 생성한다. 결정론적 백본(스케줄·
조립)은 스크립트로, 본문 집필은 참여연구원별 서브에이전트로 처리한다.

## 진행 절차

먼저 `research-note-toolkit` 스킬의 SKILL.md 를 읽고 그 워크플로우를 따른다. 요약:

1. **입력 파악 → config.json**: 참여연구원 로스터(대개 Excel: 이름·작성기간·근거자료·확인자)와
   `연구노트 양식.docx` 구조를 읽고 `config.json` 작성(`references/config-schema.md`,
   `assets/config.example.json` 참조). **작성자=확인자 동월 중복이 없는지** 확인.
2. **스케줄**: `python scripts/build_schedule.py config.json <work_dir>` →
   `schedule.json` / `schedule.csv` / `entries_by_writer.json`. 검증줄에서
   `self-confirmations=0`, 주당 1~2명 확인.
3. **자료 준비**: `extract_sources.py`(pptx/docx 텍스트, 보고서 그림), 슬라이드 삽입 시
   `capture_slides.py`, PDF 는 `pdf-converter` 플러그인으로 변환.
4. **본문 집필(병렬)**: 참여연구원별로 `note-writer` 에이전트를 띄워
   `notes_<writer>.json` 생성. 근거자료 존재 사실만 사용(anti-hallucination),
   같은 자료 공유 시 관점 분리.
5. **그림 매핑(선택)**: `figure_map.json`(page→이미지) 생성
   (`references/notes-and-figures.md`). `no_figure_writers` 는 제외.
6. **조립**: `python scripts/assemble_docx.py config.json <work_dir>` → 통합 .docx.
7. **1페이지 검증**: `python scripts/render_check.py output.docx <work_dir>/schedule.json`.
   `total_pages` = 앞뒤표지 + 노트수, `overflow_notes=NONE` 확인. 오버플로 시 그림 축소
   (`figure_max_cm`) 또는 해당 노트의 긴 줄 단축 후 재조립·재검증.
8. **최종 점검**: 날짜 평일·확인자 규칙·자기확인 없음·전 페이지 내용 유무 확인, PDF 몇 쪽을
   이미지로 렌더해 육안 확인.

## 인자

- `$ARGUMENTS` 로 작업 폴더나 config 경로가 오면 그것을 사용. 없으면 현재 폴더에서 양식/로스터를
  찾아 사용자에게 확인.

## 기존 통합본 서식 수정 요청 시

전체 재생성이 아니라, 사용자가 편집한 페이지의 서식(앞/뒤 빈줄·그림 유무·푸터 정렬·꼬리 채움)을
분석해 **미편집 페이지에만** 동일 서식을 적용한다. 텍스트가 바뀌지 않았음을 먼저 대조하고, 반드시
7단계(렌더 검증)로 마무리한다(빈줄·그림 추가가 오버플로의 주원인).
