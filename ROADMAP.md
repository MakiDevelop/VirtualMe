# Public roadmap status

**As of 2026-09-11**, GitHub issues from May 2026 are **not** an active delivery queue for this public repository.

This repo is the OSS extract (interview → local persona files, SQLite L1/L2 memory, constitution / runtime gates as documented in [CHANGELOG.md](CHANGELOG.md)). Product-side work is not tracked by those tickets.

## Closed as not planned (May 2026 wishlist)

| Issue | Title | Why closed |
|-------|--------|------------|
| [#5](https://github.com/MakiDevelop/VirtualMe/issues/5) | Pluggable MemoryBackend Protocol (SQLite + memory-hall) | Not being implemented on the public extract |
| [#6](https://github.com/MakiDevelop/VirtualMe/issues/6) | Persona-directed vs goal-oriented dialogue modes | Same |
| [#7](https://github.com/MakiDevelop/VirtualMe/issues/7) | Open-weight model support (SinkTrack + Letta + PSI) | Same |
| [#9](https://github.com/MakiDevelop/VirtualMe/issues/9) | Replace token-cosine with bge-m3 for PPA retrieval | Same |
| [#10](https://github.com/MakiDevelop/VirtualMe/issues/10) | L3 Reflective + L4 Corrective memory layers | Same |

SQLite remains the default memory backend here. [memory-hall](https://github.com/MakiDevelop/memory-hall) stays a complementary OSS project, not a promised v0.5 integration on this repo.

If any of the above returns, it will be a **new** issue with a current spec — not a revival of the May tickets.

PR [#27](https://github.com/MakiDevelop/VirtualMe/pull/27) (interview briefing context) is closed as stale / conflicting against `main`.
