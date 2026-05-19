from virtualme.interview.turn_reasoner import BASELINE_SYSTEM_PROMPT, load_system_prompt


def test_load_system_prompt_defaults_to_public_baseline():
    assert load_system_prompt() == BASELINE_SYSTEM_PROMPT


def test_load_system_prompt_reads_private_prompt_file(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("private prompt\n", encoding="utf-8")

    assert load_system_prompt(str(prompt)) == "private prompt"
