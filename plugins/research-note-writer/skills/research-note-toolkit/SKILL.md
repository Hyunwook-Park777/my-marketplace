---
name: research-note-toolkit
description: >-
  Generate a multi-year research notebook (연구노트) as a single Word document from a
  blank form template, a roster of participating researchers, and their source materials
  (PowerPoint decks, final reports, converted PDFs). Builds a holiday-aware writing
  schedule (weekday record dates, monthly per researcher, 1-2 writers per week,
  confirmation dates 5-10 workdays later), writes grounded per-researcher note content,
  inserts captured slides / report figures, and assembles a form-filled .docx where every
  note fits exactly one page. Use this whenever the user wants to create, backfill, or
  bulk-generate research notes / lab notebooks / 연구노트 / 연구일지 over a date range for
  one or more researchers — especially when they mention a 연구노트 양식(.docx), 참여연구원
  Excel roster, monthly entries, record/confirmation dates, 공휴일 제외, or filling a
  notebook from reports/presentations. Also use when adjusting an existing generated
  notebook's formatting (blank-line layout, name spacing, footer alignment, one-page fit).
---

# Research Note Toolkit

Produce a complete, believable multi-year 연구노트 (research notebook) as one Word
document. The work splits into a **deterministic backbone** (schedule + document
assembly, handled by the bundled scripts) and a **content layer** (grounded note text,
written by subagents from real source materials). Keeping these separate is what makes
the result both correct (dates, roster, one-page layout never drift) and credible (every
note reflects real material, not invented facts).

## When to reach for this

The user has a blank 연구노트 form (.docx), a list of participating researchers with the
periods they were active, and materials each researcher should have "studied" (a slide
deck, a final report, journal papers/PDFs). They want the notebook filled in across a
date range — typically monthly per researcher — with proper record/confirmation dates,
holidays excluded, and one page per entry. This skill also handles reformatting an
already-generated notebook (spacing, blank lines, figures, one-page fit).

## Prerequisites

Python packages: `python-docx`, `openpyxl`, `python-pptx`, `holidays`, `Pillow`,
`pymupdf`, and (Windows, for slide capture + page-count verification) `pywin32` with
Microsoft PowerPoint/Word installed. Converting source PDFs to Markdown is best done
with the `pdf-converter` plugin.

## Workflow

Work through these phases. Phases 1-2 and 6-8 are mechanical (run the scripts); phases
3-5 are where judgement and subagents come in.

### 1. Read the inputs, write config.json

Read the researcher roster (often an Excel file) to learn, for each person: the months
they wrote, which source material grounds their notes, and who confirmed their notes in
each period. Read the .docx template to confirm it has the expected note-page structure
(see `references/template-anatomy.md`). Then write a `config.json` — schema and a worked
example are in `references/config-schema.md` and `assets/config.example.json`.

Sanity-check the roster logic before proceeding: a person must never be both a writer and
the confirmer in the same month (no one signs off their own note).

### 2. Build the schedule

```
python scripts/build_schedule.py config.json <work_dir>
```

This emits `schedule.json` (the chronological page order — page 1 is the first entry),
`schedule.csv` (for eyeballing), and `entries_by_writer.json` (the per-writer task lists
the note-writer agents consume). It prints a validation summary — confirm
`self-confirmations=0` and `max writers/week` is 1-2 before moving on.

### 3. Prepare source material

Make each source readable/insertable:
- **Slide deck**: `python scripts/extract_sources.py pptx deck.pptx pptx_full.txt` for the
  text, and `python scripts/capture_slides.py deck.pptx slides` if slides will be inserted
  as figures (see phase 5).
- **Report (.docx)**: `python scripts/extract_sources.py docx report.docx report_full.txt`,
  and `python scripts/extract_sources.py figures report.docx report_figs` for its figures.
- **PDF papers**: convert with the `pdf-converter` plugin, then use the Markdown text as
  grounding and a representative image per paper as a figure.

### 4. Write the note content (subagents)

For each writer, spawn a subagent (see `agents/note-writer.md` for the full brief) that
reads that writer's entries from `entries_by_writer.json` and the assigned source, then
writes one grounded note per entry to `notes_<writer>.json`. Split the source across the
writer's dated entries in chronological order; where the material runs out, have them add
comparison/synthesis entries rather than invent facts.

The single most important rule: **notes may only state what is actually in the source
material.** Preserve real numbers and terms. Note length and line rules that keep each
note on one page are in `references/notes-and-figures.md`. Run writers in parallel — they
are independent — and give each a distinct lens if two writers share a source, so their
notes don't duplicate.

### 5. Build the figure map (optional but recommended)

If notes should carry a figure, emit `figure_map.json` mapping each page to one image
(captured slide / report figure / paper image). Guidance and the mapping strategies are
in `references/notes-and-figures.md`. Writers listed in `no_figure_writers` are skipped.

### 6. Assemble the document

```
python scripts/assemble_docx.py config.json <work_dir>
```

This clones the template's note page into one page per schedule entry and fills each:
blank / title / blank / content / blank / figure + trailing blanks, spaced+centred footer
names, correct dates, and a page break before each note.

### 7. Verify one-page-per-note

Whether each note fits one page can only be known after Word paginates, so render it:

```
python scripts/render_check.py output.docx <work_dir>/schedule.json
```

Expect `total_pages` = (front/back matter pages) + (number of notes), and
`overflow_notes=NONE`. If notes overflow, the usual causes and fixes are: figures too
large (lower `figure_max_cm`), or figure-less notes over-filled (the assembler already
caps trailing blanks — if a few still spill, they have long wrapping lines; shorten those
lines in the notes). Re-assemble and re-render until clean.

### 8. Final checks

Confirm dates are weekdays, confirmers follow the roster, no self-confirmation, and every
page has content. Spot-render a few PDF pages to images and look at them — one figure
page and one figure-less page — to confirm layout and grounding read well.

## Adjusting an already-generated notebook

If the user hand-edited some pages and wants the rest to match, don't regenerate blindly.
Read one edited page and one unedited page, diff their structure (leading/after-title
blanks, figure presence, footer alignment, trailing fill), and apply only the missing
formatting to the untouched pages — leaving the user's edited pages alone. Verify text is
unchanged before reformatting so you don't clobber manual edits, and always finish with
phase 7 (render) because added blanks/figures are exactly what pushes notes past one page.

## Scripts

| script | purpose |
|--------|---------|
| `scripts/build_schedule.py` | roster + holidays → schedule.json / .csv / entries_by_writer.json |
| `scripts/extract_sources.py` | pptx/docx → text; docx → embedded figures |
| `scripts/capture_slides.py` | pptx → slides/slide_XXX.png (PowerPoint COM) |
| `scripts/assemble_docx.py` | template + schedule + notes + figures → filled .docx |
| `scripts/render_check.py` | Word → PDF; report total pages + overflow notes |

## References

- `references/config-schema.md` — every config.json field
- `references/notes-and-figures.md` — notes_*.json and figure_map.json formats + rules
- `references/template-anatomy.md` — what the .docx template must contain and how it's cloned
