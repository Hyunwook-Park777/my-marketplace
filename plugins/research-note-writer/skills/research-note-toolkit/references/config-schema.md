# config.json schema

A single `config.json` drives the whole pipeline. See `assets/config.example.json`
for a filled-in example. Fields:

## Top level
| key | meaning |
|-----|---------|
| `template_docx` | Path to the blank research-note form (.docx). Must contain at least one note page = a page-number paragraph + a content table + a footer table. |
| `output_docx` | Path to write the assembled notebook. |
| `period` | `{start, end, holidays_country}`. `start`/`end` are `YYYY-MM`. `holidays_country` is an ISO code understood by the `holidays` package (e.g. `KR`, `US`, `JP`). |
| `roster` | Participating researchers (see below). |
| `confirmers` | Who signs off (see below). |
| `schedule` | `{confirm_gap_days:[lo,hi], max_writers_per_week}`. |
| `formatting` | Page layout rules (see below). |

## roster[]
One entry per researcher. `start`/`end` (`YYYY-MM`) bound the months they write in
(a researcher who joins late or leaves early just narrows this window). `source` is a
free tag that (a) is written into `schedule.json` for the note-writer agents and
(b) can be used when building `figure_map.json`.

**Roster order matters**: within each month, researchers are placed into calendar
weeks in list order, so keep the list in the order you want them to appear across the month.

## confirmers[]
Non-overlapping `{start, end, name}` windows. The confirmer active in a note's month
becomes its 확인자. The builder guarantees no one confirms their own note as long as a
person is never both a roster writer and the confirmer in the same month.

## schedule
- `confirm_gap_days`: `[lo, hi]` — confirmation date is the first **workday** between
  `lo` and `hi` days after the record date. If a long holiday swallows the whole window,
  the next workday after `hi` is used (rare; logged).
- `max_writers_per_week`: advisory; the even-spread placement keeps it at 1–2 in practice.

## formatting
| key | default | meaning |
|-----|---------|---------|
| `font` / `size_pt` | Gulim / 11 | body font |
| `figure_max_cm` | `[12.0, 6.5]` | max figure width/height; images are scaled to fit inside this box |
| `blank_before_title` / `blank_after_title` / `blank_before_figure` | true | blank lines around the title and before the figure |
| `center_footer` | true | centre-align 기록자/확인자/기록일자/확인일자 |
| `space_names` | true | render "박현욱" as "박 현 욱" in the footer |
| `fill_to_page` | true | for figure-less notes, add trailing blank lines to push the footer toward the page bottom (capped so the note never spills onto a second page) |
| `no_figure_writers` | `[]` | writers whose notes should contain **no** figure (their slides/figures are dropped) |
