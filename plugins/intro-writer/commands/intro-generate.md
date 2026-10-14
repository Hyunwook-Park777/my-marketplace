---
description: 참고 PDF 논문과 사용자 기존 논문으로 사용자 문체의 Introduction(+References, SCIE 요약)을 작성하고 인용을 원문 대조 검증합니다
argument-hint: "[참고 PDF 폴더] [내 논문 PDF 폴더 또는 style_profile.json] [연구 주제]"
---

# Intro Writer Orchestrator (v2.5.0)

참고 PDF 논문을 변환·요약하고, 사용자 문체를 분석해 Introduction 을 쓰고,
인용을 원문과 대조 검증한 뒤 참고문헌까지 붙여 넘긴다.

오케스트레이터는 직접 변환·분석·집필·검증하지 않고 각 단계를 전담 에이전트에 맡긴다.
단계마다 결과 파일을 확인한 뒤 다음으로 넘어간다.

```
INPUT: ref_pdf_folder, (user_pdf_folder | style_profile), research_topic, key_contributions?
  │
  ├─ Phase 0  사전 점검 ── pdf-converter 플러그인, GPU, 출력 폴더, 기존 산출물
  ├─ Phase 1  참고 PDF → md_converted/        [pdf-converter:pdf-converter] + section_marker.py
  ├─ Phase 2  문체 프로필                      재사용 | user_md/ 변환 + [intro-writer:style-analyzer]
  ├─ Phase 3  SCIE 요약 + paper_index.json    [intro-writer:paper-summarizer] + citation_tools crossref
  ├─ Phase 4  Introduction 작성               [intro-writer:intro-writer]
  ├─ Phase 5  인용 검증 (최대 2회 수정)         citation_tools check + [intro-writer:citation-verifier]
  └─ Phase 6  References 생성·부착 + 완료 보고  citation_tools references --embed
```

---

## 1. 입력

| 항목 | 필수 | 설명 | 기본값 |
|------|------|------|--------|
| `ref_pdf_folder` | ✔ | 참고 논문 PDF 폴더 | – |
| `user_pdf_folder` | △ | 사용자 기존 논문 PDF 폴더 (3편 이상 권장) | – |
| `style_profile` | △ | 이미 만든 `style_profile.json` 경로 — 주면 Phase 2 변환·분석 생략 | – |
| `research_topic` | ✔ | 작성할 논문의 연구 주제 | – |
| `key_contributions` | | 핵심 기여점 목록 | 빈 값 |
| `research_context` | | SCIE 요약 Relevance 평가용 맥락 | `research_topic` |
| `output_dir` | | 출력 폴더 | `{ref_pdf_folder 의 상위}/intro_output/` |
| `verify_bibliography` | | Crossref 로 서지 보완·DOI 검증 (논문 제목만 전송) | `true` |

△ = `user_pdf_folder` 와 `style_profile` 중 하나. 둘 다 없으면 기본 패턴으로 쓸지 사용자에게 묻는다.

이후 단계에서 쓰는 `{style_profile_path}` = 사용자가 준 `style_profile` 경로, 없으면 `{output_dir}/style_profile.json`.

필수 입력이 빠졌으면 AskUserQuestion 으로 한 번에 묻는다. 인자로 받은 경로는 따옴표로 감싸 쓴다 (폴더명에 공백이 흔하다).

---

## 2. 스크립트 경로

`intro-toolkit` 스킬의 스크립트를 쓴다. 아래 순서로 `{scripts}` 를 정한다:

1. `${CLAUDE_PLUGIN_ROOT}/skills/intro-toolkit/scripts` (환경변수/치환이 있으면)
2. Glob `~/.claude/plugins/cache/*/intro-writer/*/skills/intro-toolkit/scripts/citation_tools.py` 의 폴더 (버전이 여럿이면 가장 높은 것)
3. Glob `**/intro-writer/skills/intro-toolkit/scripts/citation_tools.py`

못 찾으면 중단하고 경로를 보고한다. 스크립트를 새로 작성해 대체하지 않는다.
(`**/md_postprocessor.py` 같은 넓은 검색은 pdf-converter 플러그인의 같은 이름 스크립트를 잡으므로 쓰지 않는다.)

---

## 3. Phase 0: 사전 점검

1. **pdf-converter 플러그인**: 사용 가능한 에이전트 목록에 `pdf-converter:pdf-converter` 가 있는지 확인.
   없으면 중단하고 안내: `/plugin install pdf-converter@my-marketplace`
   (intro-writer v2.5 는 자체 Marker 변환기를 없애고 MinerU 기반 pdf-converter 에 변환을 맡긴다)
2. **출력 폴더에 이전 산출물이 있으면** 재사용할지 묻는다 — 변환은 GPU 로 수십 분 걸린다:
   - `md_converted/*.md` 가 PDF 수만큼 있으면 Phase 1 생략 가능
   - `style_profile.json` 이 있으면 Phase 2 생략 가능
   - 덮어쓸 파일은 `{output_dir}/_backup/` 폴더에 `_backup_YYYYMMDD_재작성` 접미어로 백업 후 진행
     (`md_converted/` 안에 백업을 두면 다른 논문으로 오인된다)
3. PDF 개수 확인: 참고 논문 2편 미만이면 진행 여부를 묻는다
4. **GPU**: 변환이 필요한 경우에만 `python -c "import torch; print(torch.cuda.is_available())"` 확인.
   False 면 pdf-converter 가 종료 코드 3 으로 멈추므로, 변환을 건너뛸 수 있는(이미 변환된 MD 가 있는) 경우가 아니면 중단하고 알린다

---

## 4. Phase 1: 참고 논문 변환

```
Agent(subagent_type="pdf-converter:pdf-converter")
"다음 폴더의 PDF 논문들을 Markdown 으로 변환해 주세요 (배치, 엔진 auto).
 입력 폴더: {ref_pdf_folder}
 출력 폴더: {output_dir}/md_converted/
 후처리·이미지 검증·변환 품질 검증까지 수행하고, 파일별 점수와 실패 목록을 보고해 주세요."
```

이어서 섹션 마커 삽입 (본문은 바꾸지 않음, 여러 번 실행해도 결과 동일):

```bash
python "{scripts}/section_marker.py" --input-dir "{output_dir}/md_converted" --report "{output_dir}/md_converted/section_report.json"
```

**통과 기준**: 변환 성공 ≥ 1편 (0편이면 중단하고 conversion_report 의 오류를 보고), 품질 verdict
(`md_converted/verification_report.json` 의 파일별 `verdict`, 없으면 이 기준은 건너뜀) `poor` 인 파일과 Introduction 마커가 없는 파일은 목록으로 보고하고
제외할지 묻는다 (Introduction 을 못 찾은 논문은 요약·인용 품질이 떨어진다).

## 5. Phase 2: 문체 프로필

- `style_profile` 을 받았으면: `intro-writer:style-analyzer` 에 `existing_profile={style_profile_path}` 로 넘겨 검증만 한다
- 아니면:
  1. `pdf-converter:pdf-converter` 로 `{user_pdf_folder}` → `{output_dir}/user_md/` 변환
     (GPU 하나를 나눠 쓰므로 Phase 1 과 동시에 돌리지 않는다)
  2. `section_marker.py --input-dir "{output_dir}/user_md"`
  3. `intro-writer:style-analyzer`: "MD 폴더 {output_dir}/user_md/ 의 Introduction 스타일을 deep 분석해
     {output_dir}/style_profile.json 을 만들고, style_confidence.md 내용은 최종 메시지로 돌려주세요." → 오케스트레이터가 `{output_dir}/style_confidence.md` 로 저장

**통과 기준**: `{style_profile_path}` 존재, `metadata.overall_confidence` ≥ 0.70. 미만이면 사용자에게 알리고 계속할지 묻는다.

Phase 2 의 style-analyzer 와 Phase 3 의 paper-summarizer 는 서로 독립이므로 **한 메시지에서 병렬로** 띄운다
(변환이 끝난 뒤).

## 6. Phase 3: 요약 + 서지 인덱스

```
Agent(subagent_type="intro-writer:paper-summarizer")
"MD 폴더: {output_dir}/md_converted/
 요약 폴더: {output_dir}/md_summary/ (summary_index.md 내용은 최종 메시지로 반환)
 서지 인덱스: {output_dir}/paper_index.json
 연구 맥락: {research_context}"
```

오케스트레이터가 반환된 인덱스 표를 `{output_dir}/md_summary/summary_index.md` 로 저장한다.

`verify_bibliography` 가 true 면:

```bash
python "{scripts}/citation_tools.py" crossref --index "{output_dir}/paper_index.json"
```

`doi ... rejected` 줄이 나오면 그 논문의 요약 DOI 가 틀렸던 것이다 — 완료 보고에 포함한다.
네트워크 실패는 경고만 남기고 계속한다.

## 7. Phase 4: Introduction 작성

```
Agent(subagent_type="intro-writer:intro-writer")
"참고 논문 MD: {output_dir}/md_converted/
 요약: {output_dir}/md_summary/
 서지 인덱스: {output_dir}/paper_index.json
 스타일 프로필: {style_profile_path}
 연구 주제: {research_topic}
 핵심 기여점: {key_contributions}
 스크립트 폴더: {scripts}
 출력 폴더(output_dir): {output_dir}
 출력: {output_dir}/Introduction.md, {output_dir}/intro_sources.json"
```

## 8. Phase 5: 인용 검증 루프

1. 구조 점검 (결정적):
   ```bash
   python "{scripts}/citation_tools.py" check --intro "{output_dir}/Introduction.md" --sources "{output_dir}/intro_sources.json" --index "{output_dir}/paper_index.json" --output "{output_dir}/citation_structure.json"
   ```
   `citation_style.format` 이 `author_year` 면 `--no-numbered`. 종료 코드 1 이면 intro-writer 에 errors 를 넘겨 고치게 한다
   (같은 라운드 안의 수정으로 치고, 라운드 수에 넣지 않는다).
2. 내용 검증 (독립 에이전트):
   ```
   Agent(subagent_type="intro-writer:citation-verifier")
   "Introduction: {output_dir}/Introduction.md
    출처 매핑: {output_dir}/intro_sources.json
    원문 MD: {output_dir}/md_converted/
    서지 인덱스: {output_dir}/paper_index.json
    출력: {output_dir}/citation_check.json (citation_check.md 내용은 최종 메시지로 반환)"
   ```
   → 오케스트레이터가 반환 내용을 `{output_dir}/citation_check.md` 로 저장
3. `status` 가 `revise` 면 intro-writer 를 **수정 모드**로 호출한다 (`revision_request` = `supported` 가 아닌 모든 항목).
   순서: 검증 → 수정#1 → check+검증 → 수정#2 → check+검증(최종). **수정은 최대 2회**이고, 마지막 검증은 항상 돌려
   `citation_check.md` 가 최종 원고와 맞게 한다. 그래도 남은 항목은 고치지 말고 완료 보고에 "미해결 인용" 으로 표시해 사용자가 판단하게 한다.

## 9. Phase 6: References 부착 + 완료 보고

```bash
python "{scripts}/citation_tools.py" references --sources "{output_dir}/intro_sources.json" --index "{output_dir}/paper_index.json" --output "{output_dir}/References.md" --embed "{output_dir}/Introduction.md" --style vancouver
```

`citation_style.format` 이 `author_year` 면 `--style authoryear`. `incomplete` 로 나온 항목(DOI·권·쪽 없음)은 보고에 포함.
종료 코드 1 (`source_file not in paper_index.json`) 이면 paper-summarizer 에 해당 파일의 서지 항목만 추가하게 하고
`crossref` → `references` 를 다시 돌린다. References 를 손으로 쓰지 않는다.

완료 보고 (한국어):

```
Intro Writer 완료 — {output_dir}

산출물
  Introduction.md      W 단어 / P 단락 / 인용률 Z% (References 포함)
  References.md        N 편 (서지 미완 K 편: ...)
  intro_sources.json   문장-출처 매핑
  citation_check.md    검증: supported A / 수정 후 해결 B / 미해결 C
  style_profile.json   신뢰도 X% (재사용 여부)
  md_summary/          SCIE 요약 N 편 + paper_index.json
  md_converted/        참고 논문 MD N 편 (변환 품질 평균 Q점)

확인 필요
  - 미해결 인용: ...
  - 거부된 DOI(요약 단계 오기): ...
  - 서지 미완: ...
```

---

## 10. 하지 않는 것

- 훅·권한에 막힌 쓰기를 Bash 등으로 우회하지 않는다 (서브에이전트에게도 같은 규칙 — 11절)

- 변환·분석·집필·검증을 오케스트레이터가 직접 하지 않는다 (각 에이전트에 위임)
- References 를 LLM 이 손으로 쓰지 않는다 (`citation_tools.py references` 만 사용)
- 검증 루프를 2회 넘게 돌리지 않는다 — 남은 문제는 사람이 판단한다
- 사용자 원본 PDF 폴더에 파일을 쓰지 않는다 (출력은 `output_dir` 에만)

---

## 11. 훅·권한 차단 처리

Claude Code 는 서브에이전트가 보고서류 파일을 직접 쓰는 것을 막을 수 있다 (결과는 부모에게 돌려주라는 규칙).
그래서 보고서 성격의 파일은 처음부터 **오케스트레이터가 쓴다**:

| 파일 | 서브에이전트가 하는 일 | 오케스트레이터가 하는 일 |
|------|----------------------|------------------------|
| `md_summary/summary_index.md` | 최종 메시지에 표 내용 반환 | 파일로 저장 |
| `style_confidence.md` | 최종 메시지에 내용 반환 | 파일로 저장 |
| `citation_check.md` | 최종 메시지에 내용 반환 (`citation_check.json` 은 에이전트가 저장) | 파일로 저장 |

그 밖의 산출물(논문별 `*_summary.md`, JSON, Introduction.md)은 에이전트가 쓴다.

에이전트 결과에 `BLOCKED_WRITE:` 가 있으면:
- 해당 내용이 이 파이프라인의 정해진 산출물이면 오케스트레이터가 그 경로에 쓴다 (부모가 쓰는 것이 훅이 의도한 흐름)
- 산출물 목록에 없는 파일이면 쓰지 않고 완료 보고에 적는다

완료 보고 전 점검: 각 에이전트 결과에서 "Bash 로 대신 썼다", 파일명을 바꿔 썼다 등 **차단 우회 흔적**이 있는지 보고,
있으면 완료 보고의 "확인 필요" 에 그대로 적는다. 서브에이전트의 완료 주장은 디스크의 실제 파일로 확인한다
(파일이 없거나 수치가 다르면 주장을 믿지 않는다).
