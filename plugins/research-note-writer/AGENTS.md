# research-note-writer

다개년 연구노트(연구노트/연구일지)를 통합 Word 문서로 자동 생성하는 플러그인.

## 구성

```
research-note-writer/
├── .claude-plugin/plugin.json
├── commands/research-note-generate.md      # 8단계 오케스트레이터
├── agents/note-writer.md                   # 참여연구원별 근거기반 본문 집필
└── skills/research-note-toolkit/
    ├── SKILL.md                            # 전체 워크플로우
    ├── scripts/
    │   ├── build_schedule.py               # 로스터+공휴일 → 스케줄
    │   ├── extract_sources.py              # pptx/docx 텍스트·보고서 그림 추출
    │   ├── capture_slides.py               # pptx → 슬라이드 PNG (PowerPoint COM)
    │   ├── assemble_docx.py                # 양식+스케줄+본문+그림 → 통합 .docx
    │   └── render_check.py                 # Word→PDF, 페이지수·오버플로 검증
    ├── references/
    │   ├── config-schema.md
    │   ├── notes-and-figures.md
    │   └── template-anatomy.md
    └── assets/config.example.json
```

## 설계 원칙

- **결정론적 백본 / 내용층 분리**: 스케줄·문서조립은 스크립트(재현 가능), 본문은 서브에이전트가
  근거자료에서 집필. 이 분리가 날짜·로스터·1페이지 레이아웃의 무결성과 내용의 신뢰성을 동시에 보장.
- **anti-hallucination**: 본문은 근거자료에 실존하는 사실·수치만 사용.
- **1페이지 원칙**: 조립 후 반드시 Word 렌더링으로 노트별 1페이지 수렴(오버플로 0)을 검증.

## 사용

`/research-note-generate` 또는 "연구노트 만들어줘"류 요청 시 `research-note-toolkit` 스킬이
트리거된다. 자세한 절차는 SKILL.md 참조.

## 의존성

python-docx, openpyxl, python-pptx, holidays, Pillow, pymupdf, (Windows) pywin32 +
Microsoft PowerPoint/Word. PDF 근거자료는 `pdf-converter` 플러그인으로 변환.

## 유래

이 플러그인은 "건설기계용 300kW급 수소연소엔진" 과제의 4개년(2022.05~2025.12) 연구노트
212페이지 통합본을 생성한 실제 세션 워크플로우를 일반화한 것이다.
