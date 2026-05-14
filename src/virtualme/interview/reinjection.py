from virtualme.interview.triples import PersonaTriple

REINJECTION_INTERVAL = 20


def should_reinject(turn_count: int, interval: int = REINJECTION_INTERVAL) -> bool:
    return interval > 0 and turn_count > 0 and turn_count % interval == 0


def build_reinjection_anchor(interviewee_id: str, core_triples: list[PersonaTriple]) -> str:
    if not core_triples:
        return ""
    lines = [
        f"Stable identity anchor for {interviewee_id}:",
        "Keep the next response consistent with these durable persona facts:",
    ]
    lines.extend(f"- {triple.relation}: {triple.object}" for triple in core_triples[:5])
    return "\n".join(lines)
