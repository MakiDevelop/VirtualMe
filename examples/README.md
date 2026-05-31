# Examples

## `sample-maker/` — a generated demo persona archive

This folder is a **real export from the VirtualMe pipeline**, so you can see what
you get *before* committing to an 8-week interview.

> ⚠️ **The persona is synthetic.** `sample-maker` is a fictional composite — not a
> real person. The anchors are hand-written demo data, deliberately bilingual
> (English + Traditional Chinese) to show the CJK-aware extraction path.

What to look at:

- **[`sample-maker/START_HERE.md`](sample-maker/START_HERE.md)** — the entry point a real user would read first.
- **[`sample-maker/SOUL.md`](sample-maker/SOUL.md)** — core identity, with *triangulated* "Core Truths" (a principle that surfaced across ≥3 questions) separated from "Emerging Patterns", each with collapsible provenance.
- **[`sample-maker/manifest.json`](sample-maker/manifest.json)** — the machine-readable index that ships beside the markdown.

## Regenerate it

The archive is produced by the real export pipeline from synthetic seed data:

```bash
python scripts/seed_demo.py
```

This seeds a throwaway database with the fictional persona, runs
`virtualme.export.export_markdown`, and writes the archive to `examples/sample-maker/`.
Edit the `ANCHORS` list in [`scripts/seed_demo.py`](../scripts/seed_demo.py) to change the demo.
