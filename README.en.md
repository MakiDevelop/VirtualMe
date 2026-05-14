# VirtualMe

> Extract a person into an AI agent — through an 8-week interview, not a form.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![中文](https://img.shields.io/badge/Lang-中文-red.svg)](README.md)

---

![VirtualMe Concept](diagrams/virtualme-concept.png)

## Why this repo exists

Most "build your AI clone" courses charge $3,000–$5,000 USD. Reading their syllabi, they sell three things:

1. Templates for filling out persona files (SOUL.md / SKILL.md / VOICE.md)
2. Claude / OpenAI API tutorials
3. Cohort accountability and coach feedback

**The technical part doesn't need a $4,000 course.** VirtualMe is the open-source version of those three things.

Two more things worth saying:

- This is not another black-box product that will one day silently update and make you feel "my AI became someone else." SOUL / VOICE / BOUNDARIES are your own markdown files. Every change is visible and revertible.
- Your interview conversations **never leave your machine**. No backend, no human moderators reviewing transcripts, no cloud sync. `hard delete` actually means hard delete.

## Why now

Academia validated this path. Stanford's Joon Park et al. published [arXiv:2411.10109](https://arxiv.org/abs/2411.10109) in November 2024, demonstrating that a 2-hour interview + LLM achieves 85% GSS self-recall accuracy. Joon then productionized the technology as [Simile](https://siliconangle.com/2026/02/12/ai-digital-twin-startup-simile-raises-100m-funding/) in February 2026, raising **$100M USD** led by Index Ventures, with backing from Fei-Fei Li and Andrej Karpathy. Simile's mission: sell to enterprises predicting consumer / employee behavior.

VirtualMe uses the same academic foundation to solve the **opposite** problem:

> **Simile validates the technology by giving enterprises the closed tools to predict others. VirtualMe applies the same foundation to give individuals the open-source tools to extract themselves.**

The window is short. Open-source personal AI extraction is nearly empty (see [`07-related-work.md`](specs/07-related-work.md) for a verified survey). If you want this technology — and want to own your own markdown files rather than another SaaS account — now is when this is worth your attention.

## The core flip: don't fill forms — get interviewed

Form-filled persona files are **performative**. Most people describe who they *want to be*, not who they *are*. The result is an AI agent that sounds like a LinkedIn bio.

VirtualMe replaces the form with a **therapist-style depth interview**:

- One question at a time, then **probe the rationale**
- Five-rule decision tree (R1–R5): fact → pattern → principle → counter-example → triangulation
- Only **triangulated principles** (surfaced in ≥3 different questions) become SOUL anchors
- Behavioral samples and failure cases weighted higher than abstract self-description

## Academic grounding

Stanford / Joon Park et al. ([arXiv:2411.10109](https://arxiv.org/abs/2411.10109)) demonstrated that a **2-hour interview + LLM** can reproduce an interviewee's General Social Survey answers with **85% accuracy** — higher than the interviewee themselves answering again after one week.

VirtualMe extends this into a production pipeline:
- Interview spread over 8 weeks × 30 min (≈ 4–6 hours total, well above the 2-hour threshold)
- Voice samples collected alongside for retrieval-augmented agent responses
- Two blind-test gates (Week 5, Week 8) catch overfitting before shipping

## What you get after 8 weeks

Eight markdown files (your archive):

| File | Contains |
|---|---|
| `SOUL.md` | Identity, values, red lines |
| `VOICE.md` | Tagged voice samples (retrieval-augmented) |
| `SKILL.md` | Domain-specific know-how |
| `PEOPLE.md` | Relationship schemas |
| `HISTORY.md` | Life narrative |
| `JOURNAL.md` | Event log (monthly update) |
| `BOUNDARIES.md` | Refusal list + PII rules + persona update protocol |
| `STATE.md` | Current state (monthly update) |

Plus a working agent endpoint that can:
- Draft messages to clients / counterparties / peers
- Reply to public posts in your voice
- Triage incoming messages
- Always `draft → human review → ship`, never autonomous

## What this is NOT

- ❌ Not a chatbot platform. An extraction pipeline that produces files you can run through any LLM.
- ❌ Not a fine-tune. Prompt-layer + retrieval. Cheap, fast, replaceable.
- ❌ Not autonomous. Every outgoing message is `draft → human review → ship`.
- ❌ Not a course. No cohort, no coach, no certificate. Read the spec, fork the repo, run it.

## Honest limitations

- Prompt-layer personas have structural ceilings on long-conversation consistency and adversarial robustness
- Real production-grade personal AI requires fine-tuning (six-figure cost)
- VirtualMe is the "good enough for 80% of daily use cases" version, not perfect fidelity
- For high-stakes decisions, the human always overrides

## Cost

- One-time: < $60 USD (Claude API for 16 interview sessions)
- Ongoing: ~$5 USD/month (monthly STATE updates + occasional agent inference)

Roughly **1.25%** the cost of a $4,000 course.

---

## Quick Start

Requirements: Python 3.11+, Anthropic API key.

```bash
git clone https://github.com/MakiDevelop/VirtualMe.git
cd VirtualMe

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY

# Initialize database
python scripts/init_db.py --path ./data/virtualme.db

# Phase 0: run one interview cycle in CLI (no LINE)
python -m virtualme.cli --interviewee yourself
```

To wire LINE / Telegram / other messaging → see `src/virtualme/transport/`.

---

## Repo Layout

```
specs/                          # Full specs (read these first)
  00-overview.md                # Start here
  01-interview-engine.md        # Interview engine, R1-R5, Question Selection
  02-question-pool.md           # 70+ questions × 8 weeks, domain templates
  03-blind-test-protocol.md     # Week 5 / Week 8 blind tests
  04-tech-stack.md              # FastAPI + SQLite + Claude Opus
  05-boundaries-and-pii.md      # Ethics, privacy, informed consent, red lines
  06-three-plans.md             # Three ways to run it

src/virtualme/
  config.py                     # Pydantic Settings
  main.py                       # FastAPI app
  cli.py                        # Local CLI
  interview/
    bot.py                      # Core orchestrator (process_turn)
    depth_evaluator.py          # fact / pattern / principle classifier
    follow_up.py                # R1-R5 decision tree
    question_selector.py        # Question Selection algorithm
    anchor_extractor.py         # Extract anchors from a turn
    pii.py                      # Lightweight PII detection
  storage/
    schema.sql                  # SQLite schema
    db.py                       # Data layer
  transport/
    line.py                     # LINE webhook
    cli.py                      # CLI transport
  data/
    question-pool.yaml          # Question pool (agnostic template + domain examples)

diagrams/
  virtualme-concept.png         # System concept diagram

tests/unit/                     # Unit tests
scripts/init_db.py              # DB initialization
```

---

## Three Ways to Run It

| For who | What you do | Cost |
|---|---|---|
| **Plan A — Self** (developers) | Fork, customize, run on yourself for 8 weeks | ~$50 API |
| **Plan B — Operator** (technical helping non-technical) | Operator handles tech; interviewee chats for 8 weeks | $50–80 API |
| **Plan C — Cohort** (group) | Each member has own DB; facilitator helps | Group decides |

See [`specs/06-three-plans.md`](specs/06-three-plans.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

- Stanford research team + Joon Park et al. for the academic foundation
- Anthropic for the Claude API (and being the core LLM)
- Everyone willing to spend 8 weeks letting a bot interview them

## Contributing

Issues / PRs welcome. The scope is intentionally narrow — welcome:
- ✅ Translations (more language README versions)
- ✅ Domain-specific question pool examples (Sales / Engineer / PM / Doctor / Teacher / etc.)
- ✅ New messaging transports (Telegram / Discord / Slack / Matrix)
- ✅ Spec clarity improvements

Out of scope:
- ❌ Dashboard / admin UI (violates the design ethic — don't build things you have to babysit)
- ❌ Multi-tenant SaaS (single-pipeline is the core)
- ❌ Auto fine-tune (prompt-layer suffices for the target use case)

---

**Discuss details:** GitHub issues or DM on [LinkedIn](https://www.linkedin.com/).
