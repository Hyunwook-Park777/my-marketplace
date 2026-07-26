# Template anatomy

`assemble_docx.py` expands a blank form into one page per note by **cloning a single
"note page block"** from the template. Understanding that block is essential when a new
template doesn't assemble cleanly.

## What a note page block is

In the template body, a note page is a run of consecutive elements:

```
<w:p>   001(페이지)      </w:p>   <- page-number paragraph (marker)
<w:tbl> ...content cell... </w:tbl> <- content table (1 row x 1 cell, tall)
<w:p>                      </w:p>   <- separator paragraph
<w:tbl> 기록자/확인자 ...   </w:tbl> <- footer table (2 rows x 4 cols)
```

That is `block_len = 4` elements. The template usually ships with several such blocks
(e.g. 13 sample pages) plus front matter (cover, index table) and back matter (notices).

## How assembly works

1. Find the first page-number paragraph (text matching `\d{3}\(` such as `001(페이지)`).
2. Deep-copy the 4-element block as a reusable template.
3. Count and remove all existing sample blocks.
4. For each schedule entry, deep-copy the block, set a page break + page number, fill the
   footer table (cells `(0,1)`=기록자, `(0,3)`=기록일자, `(1,1)`=확인자, `(1,3)`=확인일자),
   fill the content cell, and splice it back in before the back matter.
5. The index table (년.월.일 / 적요 / 페이지), if present, can be annotated with the first
   page of each year.

## If your template differs

- **Different block length or ordering** (e.g. no separator paragraph): set
  `template.block_len` in config.json and confirm the footer table is the last element of
  the block.
- **Footer cell layout differs**: adjust the cell indices in `assemble_docx.py`
  `fill_footer`.
- **No page-number marker**: add one (any paragraph whose text matches `\d{3}\(`), or
  change the detection regex.

The content cell is expected to be a single tall cell (many empty paragraph lines in the
original) — the assembler clears it and rebuilds the paragraphs, so the original filler
lines don't matter, only the cell + its formatting are reused.
