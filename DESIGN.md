# Design

World: **the economics working paper**. The dashboard is set like a research paper a judge would print: a running head, a title, an abstract, numbered sections, figures and tables with numbered captions and source notes. No cards, pills, tiles or coloured boxes. Pinned by the author's brief ("thesis paper with data and graphs, not cluttered, no unnecessary boxes"), 2026-11-13.

Scene: an investor reading on a desktop screen in daylight during the judging window, so light ("paper") is the primary theme; dark follows the OS setting with its own validated steps.

## Typography
- Text and headings: a book serif from the system stack `"Iowan Old Style", "Charter", "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif`. Body near 17px on screen; the column is wide (author, 2026-11-13), so lines run long rather than leave wide side margins. No web font, because the page must load nothing from the network.
- Small caps (`font-variant-caps: all-small-caps`) for the running head, figure and table labels, and verdict words.
- Numbers in tables and charts: `font-variant-numeric: tabular-nums lining-nums`.
- One family for the whole document: the same serif sets headings, body, tables, chart labels, formulas and commands (formulas in italic), so the page reads as one typeset paper. No monospace. Confirmed by the author, 2026-11-13.

## Colors

Restrained: tinted neutrals plus one data accent.
| Role | Light | Dark |
|---|---|---|
| Ground | `#fbfaf7` | `#161615` |
| Ink | `#1b1b19` | `#ecebe6` |
| Secondary text | `#4f4d48` | `#bdbbb3` |
| Muted text | `#6b6962` | `#9a978f` |
| Rules | `#dcd8ce` | `#34332f` |
| NEAR (data accent, links) | `#1f5fae` | `#4a8ad6` |
| Peers (neutral marks) | `#8c897f` | `#7a776f` |
| Gross fees (backdrop fill, outlined in peer grey) | `#c9c5ba` | `#46443f` |
| Reference lines (peer median, k) | `#c4501f` | `#d4683a` |
| Verdict holds | `#2f7d32` | `#5fae63` |
| Verdict fires | `#b3261e` | `#e0675e` |

Accent and reference pass the dataviz validator in both modes (CVD ΔE ≥ 22, contrast ≥ 3:1); all text tokens are ≥ 5:1. Colour never carries meaning alone: verdicts are words with a small square mark, series are labelled.

## Components

Figures and tables are the only components.
- Figure captions above the figure ("Figure n." in small caps, numbered by CSS counters so no digit is typed), the takeaway sentence as the caption text, then the figure, then a "Method." note in small muted type. Sources are not repeated under each figure: they sit in one Sources section after the evidence, each entry linking back to the figures that use it (author, 2026-11-13).
- Tables without frame: no rules above or below, only a hairline under the column headers, no vertical rules, no fills, numbers right-aligned.
- Charts: hairline gridlines, muted axis text, thin bars with 1px rounding, NEAR in the accent, peers grey, the upper-bound perimeter as an outlined bar, reference lines dashed in the reference colour with a direct label.

## Layout
One wide column (about 66rem) with a 24px side gutter, 16px on phones, so the text sits close to the screen edges instead of in a narrow centred strip; spacing is tight (author, 2026-11-13). No author byline in the masthead. The method is one short paragraph and there is no glossary. Sections numbered by CSS counters; the contents as an inline list after the abstract; no rules between text and figures: spacing and headings alone separate them (author, 2026-11-13). Nothing sticky.

Print: A4 at about 9.5pt, every figure kept whole on one page; the page must print in five pages at most (author, 2026-11-13).
