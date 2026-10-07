# CareerPilot TPM — executive deck

Five-slide, 16:9 executive presentation for internship / TPM / EM interviews.

## Files

| File | Purpose |
| --- | --- |
| [`CareerPilot-TPM-Executive-Deck.pptx`](./CareerPilot-TPM-Executive-Deck.pptx) | Editable PowerPoint source |
| [`generate_deck.py`](./generate_deck.py) | Regenerates the PPTX |
| [`speaker-notes.md`](./speaker-notes.md) | ~3–5 minute walkthrough notes |
| [`qa-renders/`](./qa-renders/) | Optional PNG renders used for visual QA |

PDF exports are **gitignored** (`*.pdf`) and must not be committed (repo invariant: no tracked PDFs). Generate locally when needed.

Outline source of truth: [`../08-executive-deck-outline.md`](../08-executive-deck-outline.md).

## Regenerate PPTX

From repo root (requires `python-pptx` in the active environment):

```bash
.venv/bin/pip install python-pptx   # if needed
.venv/bin/python docs/tpm-case-study/deck/generate_deck.py
```

## Export PDF (optional, local only)

The editable source of truth is the **PPTX**. Do not commit PDF output.

If LibreOffice is installed:

```bash
soffice --headless --convert-to pdf --outdir docs/tpm-case-study/deck \
  docs/tpm-case-study/deck/CareerPilot-TPM-Executive-Deck.pptx
```

On macOS, `soffice` may be:

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice
```

`qa-renders/slide-0N.png` are optional visual-QA bitmaps (safe to commit; not PDFs).

## Slide titles

1. CareerPilot: Grounded, Human-Controlled Applications
2. Architecture + Critical Path
3. Program Plan + Risks
4. Launch Evidence + Release Provenance
5. Results, Tradeoffs, Next Step

## Design notes

- Black / white / violet accent (aligned with CareerPilot UI language, but executive — not a UI clone)
- Footer: `CareerPilot — TPM Case Study`
- Max ~5 bullets per content block; one takeaway bar per slide
- Metrics on slide 4 are **tag-time release-gate** figures — do not silently swap for current-main counts

## Fact anchors (do not overstate)

- Never auto-submits
- Not production hosted SaaS
- Fill certified for Greenhouse + Lever only
- Certified runtime `7b6c3ee…` ≠ tag `b73a983…`
- Open post-v1 PRs are backlog, not shipped v1
