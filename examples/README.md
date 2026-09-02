# Examples

## `sample-maker/` — a generated demo persona archive

This folder is a **real export from the VirtualMe pipeline**, so you can see what
you get *before* committing to an 8-week interview.

> ⚠️ **The persona is synthetic.** `sample-maker` is entirely fictional and is not
> derived from or combined from any real person's data. The anchors are hand-written
> demo data, deliberately bilingual (English + Traditional Chinese) to show the
> CJK-aware extraction path.

What to look at:

- **[`sample-maker/START_HERE.md`](sample-maker/START_HERE.md)** — the entry point a real user would read first.
- **[`sample-maker/SOUL.md`](sample-maker/SOUL.md)** — core identity shown in three maturity layers: "Validated Patterns" (cross-session evidence), "Recurring but Unvalidated Patterns", and "Emerging Patterns". Each item keeps collapsible provenance and missing-evidence notes.
- **[`sample-maker/WHY-DEPTH-MATTERS.md`](sample-maker/WHY-DEPTH-MATTERS.md)** — a one-page Traditional Chinese comparison of generic, FAQ-style, and archive-driven answers to the same request.
- **[`sample-maker/manifest.json`](sample-maker/manifest.json)** — the machine-readable index that ships beside the markdown.

## Regenerate it

The archive is produced by the real export pipeline from synthetic seed data:

```bash
uv run python scripts/seed_demo.py
```

This seeds a throwaway database with the fictional persona, runs
`virtualme.export.export_markdown` through the current promotion and hedge gates,
and writes the archive to `examples/sample-maker/`.
Edit the `ANCHORS` list in [`scripts/seed_demo.py`](../scripts/seed_demo.py) to change the demo.
