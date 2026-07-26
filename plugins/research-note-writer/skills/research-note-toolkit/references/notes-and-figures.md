# Notes JSON and figure_map JSON

## notes_*.json  (one file per writer, or a single notes.json)
The note-writer agents produce, for each writer, an array of note objects. The
assembler merges every `notes_*.json` in the work dir by `page`.

```json
[
  { "page": 1,
    "title": "[Vienna 2022-09·AVL] 고효율 수소 내연기관 설계",
    "lines": [
      "○ AVL, 12.8L HD 수소 ICE 최고 열효율 개념 발표.",
      "   - 밀러 사이클·직분사·희박연소·과급 조합 적용.",
      "○ 성능 결과: BTE >42%, BMEP 22.5 bar 달성.",
      "..."
    ] }
]
```

Rules that keep every note on one page:
- `title` ≤ ~45 chars.
- `lines`: 13–16 short bullet lines. Start each with `○ ` (topic) or `   - ` (detail).
- Keep each line ≤ ~40 Korean chars — long lines wrap and can push the note onto a 2nd page.
- Only use facts that exist in the source material (anti-hallucination). Preserve real
  numbers/terms verbatim.
- `page` must match the `page` values in `schedule.json` for that writer.

## figure_map.json  (optional)
Maps a note page to one image file. The assembler inserts it (centred, scaled to
`figure_max_cm`) after the content — unless the writer is in `no_figure_writers`.

```json
{ "1": "vienna_figs/2022-09_AVL.jpg",
  "2": "slides/slide_003.png",
  "100": "report_figs/fig_045.png" }
```

How to build it depends on the sources:
- **Captured slides**: run `capture_slides.py` → `slides/slide_XXX.png`, then map each
  pptx-based note to a slide (e.g. distribute a writer's assigned slide range across
  their dated notes in order).
- **Report figures**: run `extract_sources.py figures report.docx report_figs` and map
  report-based notes to figures (bucket by year/section if the report is structured that way).
- **PDF paper figures**: pick a representative image from each converted paper's images
  folder and map the corresponding note.

A short project-specific script is usually the clearest way to emit `figure_map.json`;
keep it deterministic so re-runs are reproducible.
