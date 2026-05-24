# VirtualMe Architecture and Demo Flow

This document is the short operator-facing map for explaining what is already running on `vm.2ch.tw` and what the demo proves.

## Production Architecture

```mermaid
flowchart LR
    User[LINE user] -->|message| LINE[LINE Messaging API]
    LINE -->|POST /webhook/line| Nginx[Nginx TLS host\nvm.2ch.tw]
    Nginx -->|proxy_pass| App[FastAPI app\nuvicorn 127.0.0.1:8000\nsystemd virtualme.service]

    App --> Consent[Consent and BYOK gate]
    Consent --> Reasoner[Interview reasoner\nquestion selector + follow-up rules]
    Reasoner --> Guardrail[Guardrail\nrefusal, fatigue, probe cap]
    Guardrail --> Store[(SQLite\nsessions, turns, anchors,\ntransport events)]

    Store --> Export[Persona archive export\n8 dimension Markdown files]
    Store --> Snapshot[Snapshot and review draft\nbehavior profile + blind test material]
    Export --> Download[Tokenized download URL\n/download/persona/{token}]
    Download --> User

    App -. health .-> Health[/GET /healthz/]
```

## What The Current Demo Shows

1. A real LINE user can talk to the deployed bot at `vm.2ch.tw`.
2. The app persists interview state locally in SQLite: sessions, turns, anchors, and transport idempotency events.
3. The interview engine does more than batch prompting: it tracks the current question, chooses follow-ups, evaluates depth, and stores source-backed anchors.
4. Export paths can generate human-editable persona files and review artifacts instead of locking the user into a platform.
5. v1.1 adds Constitution detector gates for state/trait separation, reflective restraint, self-correction, and multi-session validation. M2 will wire those detectors into runtime promotion/export decisions.

## Demo Script

### 1. Health Check

```bash
curl https://vm.2ch.tw/healthz
```

Expected shape:

```json
{"ok":"true","version":"1.1.0"}
```

### 2. LINE Interview

Send a normal answer to the LINE bot. The expected behavior is:

- the bot treats the message as an interview turn, not a one-shot prompt;
- it either asks a grounded follow-up or advances to the next selected question;
- it records the turn and any extracted anchors in SQLite;
- explicit refusal, fatigue, or probe-cap cases are routed through `Guardrail`.

### 3. Persona Export Request

Ask in LINE for a profile export, using a phrase such as:

```text
請匯出人格檔
```

Expected behavior:

- the bot checks consent, BYOK, and maturity conditions;
- it reports progress before export;
- it generates an 8-dimension persona archive;
- it returns a tokenized download URL rather than exposing raw server paths.

### 4. Review / Blind-Test Loop

Use the generated snapshot or blind-test material to answer the real product question:

```text
這個輸出像不像本人？哪一句不像？缺哪個反例？
```

The important signal is not whether the model sounds polished. The important signal is whether the pipeline can preserve evidence, uncertainty, correction routes, and user ownership while improving fidelity over multiple sessions.

## Operator Notes

- Production service: `virtualme.service`
- Production repo: `/home/virtualme/VirtualMe`
- Public host: `https://vm.2ch.tw`
- App port: `127.0.0.1:8000` behind nginx
- Health endpoint: `/healthz`
- LINE webhook endpoint: `/webhook/line`
- Runtime data: SQLite under the configured `DATABASE_URL`
- Before deployment, back up the SQLite database and verify migrations are idempotent.
