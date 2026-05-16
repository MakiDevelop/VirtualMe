from virtualme.interview.lang import length_units, tokens


def test_tokens_returns_lowercase_latin_words():
    assert tokens("Honesty BUILDS trust_1") == ["honesty", "builds", "trust_1"]


def test_tokens_returns_cjk_bigrams():
    result = tokens("誠實信任")
    assert "誠實" in result
    assert "實信" in result
    assert "信任" in result


def test_tokens_returns_mixed_latin_and_cjk_tokens():
    result = tokens("Honesty 誠實")
    assert "honesty" in result
    assert "誠實" in result


def test_tokens_returns_single_cjk_character():
    assert tokens("誠") == ["誠"]


def test_length_units_counts_latin_words_cjk_chars_and_mixed_text():
    assert length_units("honesty builds trust") == 3
    assert length_units("誠實信任") == 4
    assert length_units("honesty 誠實 trust") == 4
