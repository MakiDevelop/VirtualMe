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

[ACL Anthology link](https://aclanthology.org/2025.findings-emnlp.1098/) — "Post Persona Alignment for Multi-Session Dialogue Generation" (Chen et al., 2025)

**Claim:** Generate a general response first, then post-hoc align it to persona memory. Outperforms pre-retrieval methods on naturalness, diversity, and consistency simultaneously.

**Implication for VirtualMe:**
- This is the most promising non-fine-tune mitigation for persona drift in long conversations.
- VirtualMe roadmap should adopt PPA as the agent response pipeline. Not yet implemented.

### Persona drift quantification — arXiv:2512.12775

[arXiv:2512.12775](https://arxiv.org/html/2512.12775v1) — "Persistent Personas? Role-Playing, Instruction Following, and Safety in Long Dialogues" (Dec 2025)

**Claim:** Tested 7 SOTA LLMs (open + closed). Persona fidelity systematically degrades over long dialogues across knowledge / style / in-character consistency. Goal-oriented dialogues degrade worst (persona vs instruction-following conflict). Drift is *systematic reversion to default behavior*, not random.

**Implication for VirtualMe:**
- This is the canonical citation for "prompt-layer persona has structural ceilings."
- VirtualMe explicitly mitigates with: (1) session cap (25 min dialogue), (2) periodic identity re-injection, (3) human review of outgoing content (`draft → review → ship`).
- For autonomous multi-turn outbound use cases (e.g., multi-hour customer calls), VirtualMe is not appropriate.

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

## 3. The closest commercial counterpart

### Simile (Joon Park, B2B enterprise)

**Why it matters:** Joon Park, lead author of [arXiv:2411.10109](https://arxiv.org/abs/2411.10109), founded Simile in early 2026. Simile raised **$100M in February 2026** led by Index Ventures, with backing from Fei-Fei Li and Andrej Karpathy. ([SiliconAngle coverage](https://siliconangle.com/2026/02/12/ai-digital-twin-startup-simile-raises-100m-funding/), [TechFundingNews](https://techfundingnews.com/100m-for-stanford-spinout-simile-ai-that-simulates-human-decisions/))

**What Simile does:**
- B2B enterprise SaaS
- Trains on interview-grounded data + transaction logs + scientific journals
- Sells "predict consumer / employee behavior" to enterprises (initial customers: CVS Health, Telstra)
- Closed-source

**How VirtualMe relates:**

| | Simile | VirtualMe |
|---|---|---|
| Customer | Enterprises predicting their consumers/employees | Individuals extracting themselves |
| Data | Interview + behavioral logs + scientific journals | Interview only (the interviewee's own 8 weeks) |
| Ownership | Simile owns the model + simulations | Interviewee owns the markdown files |
| Source | Closed | Open (MIT) |
| Cost | Enterprise pricing | < $60 USD |
| Direction | Outward (model others) | Inward (extract self) |

**Position statement:** Simile validates that interview-grounded LLM simulation is a real, fundable technology. VirtualMe applies the same academic foundation to a different problem — giving individuals the open-source tools to extract themselves, instead of giving enterprises the closed tools to predict others.

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
