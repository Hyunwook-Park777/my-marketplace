---
name: intro-toolkit
description: "Toolkit for the intro-writer plugin: section markers for converted paper MD, citation checking, Crossref bibliography verification (catches wrong DOIs), Vancouver/author-year References generation, SCIE summary template, and Introduction linguistic patterns. Use when running the intro-writer pipeline (/intro-generate), or when checking an Introduction's citations, building a References list from converted papers, or verifying paper DOIs."
---

# Intro Toolkit

intro-writer 에이전트들이 공유하는 스크립트와 참조 파일.
PDF→MD 변환은 이 스킬이 하지 않는다 — `pdf-converter` 플러그인(MinerU)에 맡긴다.

## 스크립트·참조 경로

에이전트가 `{scripts}` / `{references}` 를 정하는 순서:

1. `${CLAUDE_PLUGIN_ROOT}/skills/intro-toolkit/` (치환/환경변수가 있으면)
2. Glob `~/.claude/plugins/cache/*/intro-writer/*/skills/intro-toolkit/` (버전이 여럿이면 가장 높은 것)
3. Glob `**/intro-writer/skills/intro-toolkit/`

못 찾으면 중단하고 보고한다. 대체 스크립트를 직접 작성하지 않는다.
파일명만으로 넓게 찾지 않는다 — `md_postprocessor.py` 같은 이름은 다른 플러그인에도 있다.

## Scripts

| Script | 용도 |
|--------|------|
| `scripts/section_marker.py` | 변환된 MD 에 `<!-- SECTION_START/END: X -->` 삽입. 본문 불변, 멱등. MinerU 처럼 모든 헤딩이 `#` 이어도 문구·순서로 판별 |
| `scripts/citation_tools.py crossref` | `paper_index.json` 빈 서지 필드 채움 + 기존 DOI 가 실제 그 제목을 가리키는지 검증 (틀리면 제거) |
| `scripts/citation_tools.py references` | 인용 번호 ↔ 파일 매핑과 서지 인덱스로 References 생성 (`vancouver`/`authoryear`), `--embed` 로 Introduction.md 에 부착 |
| `scripts/citation_tools.py check` | 본문 인용 ↔ references 대조, 첫 등장 순서, 인용률. 오류 시 종료 코드 1 |

```bash
python {scripts}/section_marker.py --input-dir ./md_converted --report ./md_converted/section_report.json
python {scripts}/citation_tools.py crossref   --index paper_index.json
python {scripts}/citation_tools.py check      --intro Introduction.md --sources intro_sources.json
python {scripts}/citation_tools.py references --sources intro_sources.json --index paper_index.json \
       --output References.md --embed Introduction.md --style vancouver
```

`crossref` 는 논문 제목만 api.crossref.org 로 보낸다. 오프라인이면 경고만 남기고 필드를 비워 둔다.

## References

| File | 용도 |
|------|------|
| `references/linguistic-patterns.json` | Introduction 언어 패턴 (opening, gap, objective, closing, 5단계 서사, voice/tense, 전환어, 헤징, 인용 형식). style_profile 이 없을 때 기본값 |
| `references/scie-summary-template.md` | SCIE 9-section 요약 템플릿 |

## 데이터 흐름

```
md_converted/*.md ──section_marker──▶ (마커 포함 MD)
        │
        ├─ paper-summarizer ─▶ md_summary/*_summary.md
        │                     paper_index.json ──crossref──▶ (서지 보완·DOI 검증)
        │
        └─ intro-writer ─▶ Introduction.md + intro_sources.json
                               │ check (구조) + citation-verifier (내용)
                               └─ references --embed ─▶ References.md + Introduction.md 끝 부착
```

## 파일 스키마 요약

- `paper_index.json`: `{"papers": [{file, title, authors:[{family,given}], journal, journal_abbrev, year, volume, issue, pages, doi, doc_type}]}` — 상세는 `agents/paper-summarizer.md`
- `intro_sources.json`: `{references:[{citation_number, source_file}], mappings:[{paragraph, sentence, citations, source_files, source_section, evidence, cars_move}], uncited_sentences:[...]}` — 상세는 `agents/intro-writer.md`
- `citation_check.json`: 문장별 verdict — 상세는 `agents/citation-verifier.md`
