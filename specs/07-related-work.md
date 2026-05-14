# Related Work

> Where VirtualMe sits in the literature and the wider personal-AI design space.
> Last updated: 2026-05-14 (Scout-1 / Perplexity Max research pass).

---

## 1. Foundational paper

### Stanford Generative Agent Simulations (Park et al., 2024)

[arXiv:2411.10109](https://arxiv.org/abs/2411.10109) — "Generative Agent Simulations of 1,000 People" / "LLM Agents Grounded in Self-Reports Enable General-Purpose Behavior"

**Headline finding:** a 2-hour qualitative interview, transformed into an LLM agent prompt, reproduces the interviewee's answers to the General Social Survey with ~85% normalized accuracy — within 1.7 percentage points of how accurately the interviewee themselves replicates their own answers two weeks later. Even with 80% of interview content removed (24 min remaining), interview-grounded agents still outperformed demographic-composite agents by 14–15 percentage points. ([Stanford HAI summary](https://hai.stanford.edu/news/ai-agents-simulate-1052-individuals-personalities-with-impressive-accuracy))

**Why this matters for VirtualMe:**

- The 2-hour threshold is a floor, not a ceiling. VirtualMe spreads interviews over 8 weeks × 30 min = 4–6 hours total, well above floor.
- The paper's method is single-pass interview → single agent. VirtualMe extends this with progressive prototype rebuilds every 2 weeks and two blind-test gates.
- The accuracy benchmark (~85%) is on closed-form survey questions (GSS, Big Five, economic games). Open-form dialogue self-recognition is empirically lower (60–75%) — which is why VirtualMe's blind test target is 50–60%, not 85%.
- **Honest limitation:** the marginal benefit of 8 weeks vs. 2 hours has not been quantified in any published study as of 2026-05. VirtualMe's choice of 8 weeks is design judgment, not proven optimum.

### Earlier predecessor: Generative Agents (Park et al., 2023)

[arXiv:2304.03442](https://arxiv.org/abs/2304.03442) — "Generative Agents: Interactive Simulacra of Human Behavior" — the Smallville 25-agent simulation. Established memory stream + reflection + planning as core architectural primitives.

---

## 2. Closely related research (post-2411.10109)

### Personality Structured Interview (PSI) — arXiv:2502.12109

[arXiv:2502.12109](https://arxiv.org/abs/2502.12109) — "Personality Structured Interview for Large Language Model Simulation" (Feb 2025)

**Claim:** A psychometric-theory-informed structured interview matches or exceeds the 2-hour Park interview for personality simulation. Released a dataset of 357 structured interviews.

**Implication for VirtualMe:**
- PSI is theoretically grounded but narrow (personality only). VirtualMe's 8-week breadth covers SOUL/VOICE/SKILL/PEOPLE/HISTORY/BOUNDARIES — strictly more than personality.
- PSI offers a psychometric benchmark that VirtualMe could adopt for evaluation — see [`03-blind-test-protocol.md`](03-blind-test-protocol.md) future work.

### Post Persona Alignment (PPA) — EMNLP 2025 Findings

[arXiv:2506.11857](https://arxiv.org/abs/2506.11857) | [ACL Anthology](https://aclanthology.org/2025.findings-emnlp.1098/) — "Post Persona Alignment for Multi-Session Dialogue Generation" (Chen et al., RIKEN AIP + University of Tokyo, EMNLP 2025 Findings)

**Three-stage architecture:**

```
Stage 0 (preprocessing): Compress sessions into (name, relation, object) triples → memory pool
Stage 1: Generate R_g (general response, no persona conditioning)
Stage 2: Use R_g as retrieval query → top-k memory entries M_k (threshold θ=0.2, k=5)
Stage 3: Refine response with M_k context
```

**Reported benchmarks** (Table 1, multi-session LLM dialogue):

| Strategy | C-Score | P-F1 |
|---|---|---|
| DirectGen (pre-conditioning) | 0.221 | 0.092 |
| DialogRetr (pre-retrieval, ≈ VirtualMe v0.3 baseline) | 0.182 | 0.081 |
| **PPA** | **0.456** | **0.146** |
| Gold (human upper bound) | 0.554 | 0.147 |

PPA also outperforms when triples are used vs raw utterances (C-Score 0.456 vs 0.359). Prompt templates are public in the paper's appendix A.

**Implication for VirtualMe:**
- 2× improvement over VirtualMe's current pre-retrieval baseline
- Pure prompting + retrieval, no fine-tune required
- ~50 LoC change to `interview/bot.py:_final_reply()`
- Stage 1 can use Haiku (cheap), Stage 3 can use Sonnet (no need for Opus)
- Cost trade-off: breaks Anthropic prompt cache stable prefix (cache hit rate ~60% → ~30%), but Stage 1 is short, total token cost roughly balanced
- Roadmap: **v0.4 primary deliverable**

### Persona drift quantification — arXiv:2512.12775

[arXiv:2512.12775](https://arxiv.org/abs/2512.12775) | [ACL Anthology (EACL 2026 Long)](https://aclanthology.org/2026.eacl-long.246/) — "Persistent Personas? Role-Playing, Instruction Following, and Safety in Long Dialogues" (EACL 2026, published 2026-03-19)

**Claim:** Tested 7 SOTA LLMs (open + closed). Persona fidelity systematically degrades over long dialogues across knowledge / style / in-character consistency. Goal-oriented dialogues degrade worst (persona vs instruction-following conflict). Drift is *systematic reversion to default behavior*, not random.

**Critical insight for VirtualMe:** persona-directed dialogue (pure roleplay) degrades **slower** than goal-oriented dialogue (roleplay + task execution). This means the agent should structurally separate persona conversation from task execution rather than mixing both in a single session.

**Mitigation methods catalog** (synthesized across paper + related work):

| Method | Source | API-compatible? | Cost | VirtualMe |
|---|---|---|---|---|
| Periodic persona re-injection | implied by paper | ✅ yes | +tokens/turn | **v0.4** |
| Persona-directed / goal-oriented mode separation | paper §findings | ✅ yes (architectural) | free | **v0.4** |
| PPA (Post Persona Alignment) | arXiv:2506.11857 | ✅ yes | +1 LLM call | **v0.4** |
| System prompt repetition | arXiv:2402.10962 | ✅ yes | high token cost | conditional |
| Split-softmax (attention intervention) | arXiv:2402.10962 | ❌ needs open-weight | n/a | future open-weight only |
| SinkTrack (attention sink anchoring) | arXiv:2604.10027 (ICLR 2026) | ❌ needs open-weight | n/a | future open-weight only |
| Persona-Aware Contrastive Learning | arXiv:2503.17662 | ⚠️ needs contrastive data pipeline | high | v0.6 conditional |

**Implication for VirtualMe:**
- This is the canonical citation for "prompt-layer persona has structural ceilings."
- For the Anthropic-API tier, only three mitigations are usable: periodic re-injection, mode separation, PPA. All three are scheduled for v0.4.
- For autonomous multi-turn outbound use cases (e.g., multi-hour customer calls), VirtualMe is not appropriate — drift is delayed, not solved.

### Persona Ecosystem Playground (PEP) — arXiv:2603.03140

[arXiv:2603.03140](https://arxiv.org/html/2603.03140v1) — "How to Model AI Agents as Personas?" (Mar 2026)

**Claim:** Extract personas from social-media posts via RAG, validate across personas. Cross-persona accuracy 0.75 (vs 0.20 baseline).

**Implication for VirtualMe:**
- Complementary, not competing. PEP uses behavioral data (posts); VirtualMe uses interview data. Combining them is an open research direction.

### Persona-Aware Contrastive Learning (PCL) — ACL 2025 Findings

[ACL Anthology link](https://aclanthology.org/2025.findings-acl.1344/) — "Enhancing Persona Consistency for LLMs' Role-Playing"

**Claim:** Annotation-free, self-questioning + iterative contrastive learning. Significantly improves CharEval + GPT-4 evaluation vs vanilla LLM.

**Implication for VirtualMe:** conditional — requires contrastive training infrastructure. Roadmap item for v2 if Path A blind-test fails.

### Self-Clone Framework — UBC CHI 2026

[CHI 2026 paper (UBC)](https://www.cs.ubc.ca/labs/socius/files/papers/chi2026-selfclone.pdf) — "Cloning the Self for Mental Well-Being: A Framework for Designing Self-Clone Chatbots"

**Claim:** Academic framework for self-clone chatbots as AI-mediated self-interaction tools, with ethical guardrails (preventing negative self-schema reinforcement, data privacy, user agency).

**Implication for VirtualMe:** parallel academic validation. VirtualMe's [`05-boundaries-and-pii.md`](05-boundaries-and-pii.md) draws on the same ethical traditions but is engineering-driven rather than research-driven.

---

## 3. The closest commercial counterparts

### Simile — B2B enterprise (Joon Park)

**Why it matters:** Joon Park, lead author of [arXiv:2411.10109](https://arxiv.org/abs/2411.10109), founded Simile in early 2026. Simile raised **$100M in February 2026** led by Index Ventures, with backing from Fei-Fei Li and Andrej Karpathy. ([SiliconAngle](https://siliconangle.com/2026/02/12/ai-digital-twin-startup-simile-raises-100m-funding/), [TechFundingNews](https://techfundingnews.com/100m-for-stanford-spinout-simile-ai-that-simulates-human-decisions/))

**Simile's B2B side:**
- Trains on interview-grounded data + transaction logs + scientific journals
- Sells "predict consumer / employee behavior" to enterprises
- Customers: CVS Health (merchandising), Wealthfront (qualitative research at 15× scale), Suntory (product development), Gallup (panel data access) ([implicator.ai coverage](https://www.implicator.ai/the-stanford-team-that-invented-generative-agents-wants-to-kill-the-focus-group/))
- Use case Park mentioned on Bloomberg TV: "predict 8 of 10 earnings call questions"
- Closed-source

VirtualMe vs Simile B2B: different problems entirely (predict-others vs extract-self). No real overlap.

---

### Simile MiniMe — B2C consumer (DIRECT competitor)

**[minime.simile.ai](https://minime.simile.ai)** — Simile's consumer product. Personal users go through ~10 minutes of interview, get their own AI agent.

**This is VirtualMe's direct competitor.** Both target individuals building agents of themselves. Comparison:

| | Simile MiniMe | VirtualMe |
|---|---|---|
| Interview length | ~10 minutes (single session) | 8 weeks × ≤30 min (4–6 hours total) |
| Method | Likely structured / brief | Therapist-style depth interview + R1–R5 follow-up |
| Verification | Not publicly documented | Blind test at Week 5 + Week 8 |
| Data ownership | Held by Simile | Markdown files owned by interviewee |
| Source | Closed | Open (MIT) |
| Cost | Unknown (likely bundled subscription) | ~$60 one-time + $5/month |
| Customization | Platform-defined | Fork-and-modify |
| Audit / transparency | Black-box updates | Git-tracked changes |
| Persona update protocol | Platform decides | [BOUNDARIES.md §6](05-boundaries-and-pii.md) requires confirmation |

**Honest positioning:**

VirtualMe is NOT trying to compete on speed or polish. It is offering a different trade-off:
- **MiniMe** → fast, low-effort, locked into Simile's platform
- **VirtualMe** → slow, high-depth, open-source, you own everything

People wanting a 10-minute snapshot inside Simile's growing ecosystem should pick MiniMe. People wanting depth + sovereignty + fork-ability should pick VirtualMe. These are different products with different audiences; the comparison table exists for clarity, not for arguing one is universally better.

**Strategic implication:** the Simile family (B2B + MiniMe + future) now owns the "interview-grounded persona" category in commercial AI. VirtualMe's role in this ecosystem is to be the **open-source alternative** people can fork, modify, audit, and own. That's the position to hold — not "we're better than Simile."

---

## 4. Adjacent open-source projects

Verified open-source projects in the "interview-based personal AI" neighborhood. None implement the full VirtualMe spec (depth interview + R1–R5 + blind test + 8-week pipeline + persona artifact layering), but several are useful references.

### danielrosehill / Agentic-Context-Development-Interview-Demo

[GitHub](https://github.com/danielrosehill/Agentic-Context-Development-Interview-Demo) — AI agent conducts structured interviews → extracts personal context → injectable into RAG pipeline. Markdown-portable.

**Difference:** structured interview, but no therapist-style depth (no R1–R5 rules), no blind test, no SOUL/VOICE/SKILL persona layering. Last updated ~Feb 2025, low activity. Treats this space as engineering sketch rather than complete pipeline.

### danielrosehill / Personal-RAG-Agent-Workflow

[GitHub](https://github.com/danielrosehill/Personal-RAG-Agent-Workflow) — Same author. AI interview bot building personal RAG pipeline. Same gaps as above.

### Polysona (LilMGenius)

[GitHub](https://github.com/LilMGenius/polysona) — "Polygonal Persona": 10 psychology frameworks (Western depth, Western supplement, Eastern reflection) for interviewing, extracting conscious goals.

**Difference:** framework-based vs. therapist-depth approach. Single-session vs. 8-week. Likely no blind-test verification. Closest existing open-source competitor in spirit, but different methodology.

### AlanY1an / echovessel

[GitHub](https://github.com/AlanY1an/echovessel) — Local-first digital persona engine for characters, companions, fictional personas, personal echoes.

**Difference:** character roleplay focus, not self-extraction. Local-first architecture.

### Hackshaven / digital-persona

[GitHub](https://github.com/Hackshaven/digital-persona) — Modular AI persona system.

**Difference:** general modular system, no specific interview methodology. Limited public detail.

---

## 5. Two architectural paths

### Path A: prompt-layer + retrieval (VirtualMe's path)

**How:** the LLM stays untouched. A system prompt describes the persona (SOUL.md). Voice samples sit in an embedding store, retrieved at inference time and injected into prompts on a per-query basis.

| Pros | Cons |
|---|---|
| ~$10s/month operating cost | Structural ceiling on adversarial robustness ([arXiv:2512.12775](https://arxiv.org/html/2512.12775v1)) |
| Provider-portable (switch LLM with same files) | Long-context drift on extended conversations |
| Immediately editable by humans (markdown) | Cannot deeply internalize voice — only retrieve |
| No training data leakage | Token cost scales with retrieval k |

### Path B: fine-tune

| Pros | Cons |
|---|---|
| Internalized voice — no retrieval needed | Six-figure cost |
| Better long-context consistency | Provider-locked |
| Harder to drift in adversarial inputs | Hard to edit (need re-tune to fix) |
| | Training data persists in weights (deletion harder) |

### Why VirtualMe chose Path A

- Cost: 100× cheaper for the same daily use case
- Sovereignty: markdown files travel with the interviewee; weights don't
- Editability: BOUNDARIES.md changes today, takes effect tonight
- Honesty: prompt-layer's ceiling is acknowledged in the spec, not hidden

For interviewees whose Path A blind-test fails (Week 8 accuracy still >70%), the natural next step is Path B using the accumulated archive as training data. VirtualMe explicitly **does not implement Path B** — but the artifacts are exactly the data a Path B trainer would need.

---

## 6. The interview-as-extraction lineage

Treating qualitative interview as a method for extracting cognitive structure predates LLMs:

- **Cognitive task analysis** (Crandall, Klein, & Hoffman, 2006) — *Working Minds*. Structured interview for capturing tacit expert knowledge. R1–R5 follow-up rules in VirtualMe are a simplified LLM-mediated variant.
- **Therapist active-listening protocols** (Rogers, 1957 client-centered framework) — mirroring, pause tolerance, acknowledgment of weight. Adopted in [`01-interview-engine.md`](01-interview-engine.md) §2, but explicitly bounded (extraction, not therapy).
- **5 whys** (Sakichi Toyoda, Toyota Production System, ~1930s) — R2 (pattern → principle) is a softened 5-whys.

Park 2024 is the first empirical demonstration that LLMs can operationalize these older interview traditions into an automatable pipeline.

---

## 7. Roadmap items inspired by this research

| Item | Source | Status |
|---|---|---|
| Post Persona Alignment as response pipeline | EMNLP 2025 (PPA) | Roadmap (v0.4+) |
| Periodic identity re-injection every N turns | arXiv:2512.12775 mitigation | Partially implemented |
| PSI-based evaluation benchmark | arXiv:2502.12109 | Roadmap |
| Memory backend integration (e.g., open-source memory engines) | 2026 memory architecture survey | Roadmap |
| Contrastive learning fine-tune (if Path A insufficient) | arXiv:2503.17662 | Conditional |

---

## 8. What VirtualMe does NOT claim

To be honest about scope:

- ❌ We do NOT claim 8 weeks is empirically the optimal interview length. The marginal benefit of 8 weeks vs. 2 hours has not been quantified in any published study as of 2026-05. The choice is design judgment based on dropout risk + breadth across dimensions.
- ❌ We do NOT claim 50–60% blind-test accuracy is the universal ship threshold. It's our calibration for "draft → human review → ship" use cases; high-autonomy use cases need higher.
- ❌ We do NOT claim to solve persona drift. We delay it. [arXiv:2512.12775](https://arxiv.org/html/2512.12775v1) shows drift is structural at prompt-layer.
- ❌ We do NOT claim therapist-style depth is the only method that works. [PSI](https://arxiv.org/abs/2502.12109) shows structured psychometric interviews are competitive for personality, and may be superior for some narrower use cases.
- ❌ We do NOT claim the question pool covers all professions. The 8 pillars generalize well; SKILL needs domain customization.
- ❌ We do NOT claim VirtualMe is better than Simile. They solve different problems (predict others vs extract self).

---

## 9. Reading list

If you want to think deeper about the design space:

- Park et al. 2024 ([arXiv:2411.10109](https://arxiv.org/abs/2411.10109)) — interview-based generative agents
- Park et al. 2023 ([arXiv:2304.03442](https://arxiv.org/abs/2304.03442)) — generative agents architecture
- "Persistent Personas?" 2025 ([arXiv:2512.12775](https://arxiv.org/html/2512.12775v1)) — drift quantification
- "Post Persona Alignment" 2025 ([ACL Anthology](https://aclanthology.org/2025.findings-emnlp.1098/)) — best non-fine-tune drift mitigation
- "PSI" 2025 ([arXiv:2502.12109](https://arxiv.org/abs/2502.12109)) — structured psychometric interview alternative
- "PEP" 2026 ([arXiv:2603.03140](https://arxiv.org/html/2603.03140v1)) — RAG-based persona modeling
- Crandall, Klein, & Hoffman (2006) — *Working Minds: A Practitioner's Guide to Cognitive Task Analysis*
- UBC CHI 2026 — [self-clone for mental well-being](https://www.cs.ubc.ca/labs/socius/files/papers/chi2026-selfclone.pdf)
- Stanford HAI — [Simulating Human Behavior policy brief](https://hai.stanford.edu/policy/simulating-human-behavior-with-ai-agents)
- Anthropic's prompt caching documentation — for cost optimization
- OWASP LLM Top 10 — when designing BOUNDARIES.md threat model

---

## 10. If you build something better

Open an issue or PR. The point of MIT-licensing this repo is so better designs can build on these primitives without re-deriving them. The spec is the contribution, not the code.
