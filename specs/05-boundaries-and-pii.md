# Boundaries, PII & Informed Consent

> Meta-rules separating archival extraction from therapy, plus PII handling and immutable red lines.

---

## 1. Core Position

VirtualMe's interview engine uses **therapist-style depth methods** (active listening, mirroring, root-cause inquiry, pause tolerance, acknowledgment of weight) as its extraction core — but it is **not** a therapy service.

| | Therapy | VirtualMe Interview Engine |
|---|---|---|
| Purpose | Healing / change / problem-solving | Archive / extract / record "who they are" |
| Practitioner | Licensed therapist | LLM bot + operator review |
| Crisis handling | Yes (referral, intervention) | None — surfaces referral to professional |
| Ethical framework | Counseling ethics (confidentiality, informed consent, non-judgment) | Adopts same framework, no legal standing |
| Legal status | Regulated helping profession | Tool, no legal standing |
| Relationship | Therapeutic course | 8-week interview phase + monthly updates |

**This distinction is not a technical detail. It is the core ethic.** The interviewee must be told this explicitly before the interview begins.

---

## 2. Informed Consent (mandatory before Week 1 first session)

The interview bot's first message to the interviewee MUST cover the following 7 items:

```
Hi {name}, before we formally start, I need to walk you through the
boundaries of this interview:

1. My method is "therapist-style depth interview" — I will follow up
   on "why" until your judgment criteria surface.
   But I am NOT a therapist, and this is NOT therapy.

2. The process may surface things you hadn't noticed (childhood,
   trauma, unresolved decisions).
   If you're uncomfortable, you can always: skip / change question /
   say "tired" / say "don't save this segment".

3. I keep confidentiality — only the operator (for quality review of
   interview transcripts) can spot-check. No one else sees what you say.

4. If you surface serious emotional signals (self-harm, suicidal
   ideation, unbearable distress), I will stop and recommend you seek
   professional help. **I cannot help at the crisis layer.**

5. What we discuss eventually becomes an AI agent. You can at any time:
   - Keep some parts / delete all / modify a segment
   - After 8 weeks, decide whether to ship

6. Anything the agent writes — legally, socially, responsibility-wise —
   belongs to you, not the AI.

7. You can withdraw at any time. When you withdraw, your conversation
   archive will be:
   □ Kept (you may want to continue later)
   □ Deleted (no trace anywhere)
   Your choice.

---

To proceed with understanding and agreement, reply "I agree, let's start."
If you have questions or disagree with any item, tell me.
```

The interviewee must reply explicit consent before the interview proceeds.

---

## 3. PII Handling Rules

If the interviewee's profession involves handling third-party PII (clients, candidates, patients, students), **every interview transcript must pass PII scrubbing before storage**:

| PII Type | Handling |
|---|---|
| Third-party real names | Replace with code names: `[Person A]`, `[Person B]` |
| Company names | Replace with codes: `[Client H]`, `[Client J]` |
| Salary / compensation figures | Bucket into ranges: `180–220k` |
| Ages | Bucket: `30s`, `40s` |
| Birthdays | Reduce to month: `March`, `September` |
| Phone / email | Fully redacted |
| Third-party trauma / personal matters | Tag `confidential:counterparty`, never enters outgoing prompts |

The interviewee's own PII:
- Names, birthday, family — written to SOUL/HISTORY but **not surfaced outward**
- Childhood / marriage / health — written to SOUL/HISTORY, tagged `private:self`, blocked from outgoing prompts
- Workplace failure cases — PII-scrubbed before storage

---

## 4. Tag-Based Filtering

Every anchor carries a tag at write time. When building the outbound system prompt (agent mode), these tags filter automatically:

| Tag | Meaning | Surfaced to external prompts? |
|---|---|---|
| `public` | Public-safe | ✅ |
| `professional` | Work context only | ✅ |
| `confidential:client` | Client secret | ❌ |
| `confidential:counterparty` | Counterparty secret | ❌ |
| `private:self` | Interviewee's personal privacy | ❌ |
| `crisis:flagged` | Crisis signal | ❌ (and not stored in archive — only metadata stub) |

---

## 5. Emotional Content Handling

How the bot handles deep emotional material (corresponds to interview-engine spec §2):

**Within scope:**
- Childhood narrative, family background, career inflection points
- Resolved or actively-being-processed emotional events
- Personal feelings, evaluations of people / situations
- Surfaced-but-stable trauma (where the person has integrated the experience)

**Crisis scope (bot immediately exits interview mode):**
- Self-harm or suicidal ideation signals
- Impulse to harm others
- Uncontrolled dissociation / panic / trauma response
- Interviewee explicitly says "I can't keep going"

**Bot crisis response (verbatim — do not paraphrase):**
```
"This sounds like it needs professional support. I cannot help at the
crisis layer. I'm stopping here. When you want to continue the
interview later, tell me.

If you need help now, please consider:
- A crisis helpline in your region (e.g., 988 in the US, 1925 in
  Taiwan, Samaritans in the UK)
- Someone you trust to talk to in person"
```

The bot does NOT try to fix, continue the interview, analyze, or offer
comforting paraphrase.

---

## 6. Persona Update Protocol (after ship)

Once the agent ships, rules for modifying SOUL.md / SKILL.md / VOICE.md / etc.:

| Change type | Notification | Confirmation |
|---|---|---|
| STATE monthly update | Automatic | Not required |
| Add new SKILL anchor | Automatic | Not required |
| Modify existing SOUL anchor | Notify interviewee | Interviewee confirms |
| Delete any anchor | Notify + keep version history | Interviewee confirms |
| Modify BOUNDARIES | Force-confirm | Interviewee personally |
| Major persona shift (voice / position change) | Force-notify downstream contacts (clients / counterparties / peers) | Interviewee personally + stakeholders informed |

The last item addresses incidents like Replika users reporting their AI "felt lobotomized" after a silent persona update. Avoid sudden personality breaks visible to external parties.

---

## 7. Immutable Red Lines

Once the agent ships, these actions are **NEVER** delegable to it:

1. ❌ Issue or reject a formal offer / contract / decision
2. ❌ Sign any contract / quote / legal document
3. ❌ Publicly post unauthorized opinions (especially political, religious, or sensitive topics)
4. ❌ Handle a counterparty's crisis (refer back to the interviewee)
5. ❌ Build a deep relationship with someone the interviewee doesn't know personally
6. ❌ Move money / use budget / commit company resources
7. ❌ Modify SOUL / BOUNDARIES (only the interviewee can change these)

When the agent encounters any of the above, it surfaces:
> "This needs {interviewee} to handle personally. I'll pass it on."

---

## 8. Withdrawal & Deletion Rights

The interviewee can at any time:
- **Pause**: keep current archive, resume later
- **Withdraw** (two sub-options):
  - Retain archive (may restart in future)
  - Full deletion (no trace anywhere — SQLite + embedding store both wiped)
- **Delete a specific anchor**: by anchor ID or topic, bot removes corresponding content
- **Export**: receive their full archive (markdown + JSON) and walk away

Deletion is **hard delete**. The operator cannot recover. This is by design.

---

## 9. Meta-Rule: Modifying This Document

Changes to `BOUNDARIES.md` require:
- Interviewee personal confirmation
- Operator review
- Git commit log + persistent record
- Notification to all shipped downstream agents to reload

Boundaries cannot be silently relaxed for convenience.

---

## 10. Operator Responsibilities

Anyone running VirtualMe for someone else (operator role) accepts:

1. **Read all spec documents** before starting an interview.
2. **Spot-check transcripts** every 2 weeks for ≤15 minutes — verify bot behavior, watch for drift.
3. **Do not read transcripts gratuitously.** Confidentiality applies to operators too.
4. **Honor deletion requests** within 24 hours.
5. **Do not use interviewee data** for anything beyond what was disclosed in consent.
6. **Distinguish self-use from operating-for-others.** Running VirtualMe on yourself is one ethical context. Running it for another person is a different one with higher duty of care.

If you cannot commit to these, do not run VirtualMe for others.

---

## 11. Legal & Regulatory Context (2026-05)

This section is informational, not legal advice. Operators are responsible for their own jurisdiction's compliance.

### 11.1 VirtualMe is NOT a companion chatbot

VirtualMe is designed for **personal persona extraction and self-agent representation**, not emotional companionship. This distinction matters legally as of 2026:

- **California SB 243** (effective 2026-01-01) — the first US state regulation of "AI companion chatbots." Requires disclosure of AI identity, minor protections, crisis protocols, restricted intimate content. ([TechCrunch](https://techcrunch.com/2025/10/13/california-becomes-first-state-to-regulate-ai-companion-chatbots/), [Skadden](https://www.skadden.com/insights/publications/2025/10/new-california-companion-chatbot-law))
- **New York AI Chatbot Law** (Nov 2025) — first state to require AI companions to disclose AI identity + include self-harm detection protocols.
- **Kentucky v. Character.AI** (Jan 2026) — first state to sue an AI companion provider.
- **Character.AI + Google settlement** (Jan 2026) — settled the Sewell Setzer wrongful-death lawsuit. ([CNN](https://edition.cnn.com/2026/01/07/business/character-ai-google-settle-teen-suicide-lawsuit))

VirtualMe deliberately differs from companion chatbots:
- The "persona" represents the **interviewee themselves**, not a fictional friend
- The agent's purpose is **draft generation for human review**, not standalone emotional interaction
- No claim of persistent emotional relationship
- Bot exits to professional help on crisis signals (see §5)

### 11.2 Age requirement: 18+ only

Given the legal landscape and the depth-interview methodology's potential to surface childhood / trauma / sensitive material, **VirtualMe is restricted to adult interviewees (18+)**.

- Operators **must verify** interviewee age before starting Week 1
- This is a hard rule, not a guideline. Running VirtualMe on minors creates legal exposure regardless of jurisdiction.
- Corresponds to the elevated risk profile in [Replika's 2023 Italian DPA suspension](https://nysba.org/the-impact-of-the-eu-ai-act-on-the-use-of-ai-powered-chatbots/) (vulnerable individuals, including minors).

### 11.3 Data ownership: the interviewee owns everything

- All interview transcripts, SOUL.md / VOICE.md / etc., belong to the **interviewee**
- VirtualMe (the project, the maintainers, the operator) **do not** hold, train on, sell, or share interview data
- Deletion is honored within 24 hours and is hard delete (no backups recovered)

### 11.4 AI disclosure when using outputs externally

When the interviewee uses VirtualMe-generated content in communication with third parties (drafting LINE replies, generating LinkedIn posts, sending email):

- **Recommended:** disclose that the content was AI-generated or AI-drafted
- **Required in some jurisdictions:** EU AI Act transparency obligations apply starting 2026-08-02 to AI-generated content shown to humans. ([EU AI Act page](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai))
- For high-stakes communication (contracts, legal documents, public statements), AI disclosure is mandatory regardless of jurisdiction — see immutable red lines §7.

### 11.5 Voice / biometric data (if voice input is used)

If operators enable voice transcription:
- Voice recordings are considered **biometric data** under GDPR (and equivalent under Taiwan PDPA, California CCPA)
- Operators must have explicit legal basis for processing
- Operators should default to **discard audio after transcription** (don't persist raw voice unless legally justified)
- Transcripts retain less risk than audio but still require informed consent

### 11.6 Crisis protocol — explicit exclusion

VirtualMe is **not** a mental-health crisis intervention tool. Operators must:
- Not deploy VirtualMe as a substitute for professional mental health support
- Ensure the crisis-detection protocol (§5) is active and not disabled
- Provide region-appropriate crisis resources in their localized version

The interview engine's bot crisis response is verbatim and must not be customized to "stay engaged" with someone in crisis.

### 11.7 EU AI Act risk classification (TBD as of 2026-05)

Whether VirtualMe falls under EU AI Act Chapter III "high-risk AI system" depends on use case:
- **Self-extraction for personal use:** likely not high-risk
- **Operator-run for clients on a commercial basis:** may be high-risk if outputs influence employment / credit / education / legal decisions
- See [arXiv:2604.04604 "AI Agents Under EU Law"](https://arxiv.org/abs/2604.04604) for the current academic analysis

Commercial operators should obtain legal advice for their specific deployment.

### 11.8 Academic ethical anchor

The closest academic framework for self-clone chatbots is the UBC CHI 2026 paper, which proposes guardrails against:
- Reinforcing negative self-schema
- Inadequate data privacy
- Loss of user agency

VirtualMe's BOUNDARIES.md was designed before the UBC paper was available but converges on the same principles. ([UBC CHI 2026 paper](https://www.cs.ubc.ca/labs/socius/files/papers/chi2026-selfclone.pdf))

---

## 12. Summary

| Topic | Rule |
|---|---|
| Age | 18+ only, operators verify |
| Companion chatbot status | Not a companion; designed for self-extraction |
| Data ownership | Interviewee owns everything |
| Deletion | Hard delete within 24 hours |
| AI disclosure | Recommended always; required in EU from 2026-08-02 |
| Voice / biometrics | Discard after transcription unless legally justified |
| Crisis | Refer out, do not stay engaged |
| Minor markets | Restricted regardless of local law |

