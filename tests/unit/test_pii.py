import logging

from virtualme.interview.pii import detect_pii, scrub_pii


def test_email_scrubbed():
    result = scrub_pii("Reach me at maki@example.com")
    assert result.scrubbed_text == "Reach me at [EMAIL]"
    assert detect_pii("Reach me at maki@example.com") == ["email"]


def test_phone_scrubbed():
    result = scrub_pii("My number is 0912-345-678")
    assert "[PHONE]" in result.scrubbed_text
    assert result.redactions[0].category == "phone"


def test_chinese_name_scrubbed():
    assert scrub_pii("王小明 will join").scrubbed_text == "[Person A] will join"


def test_english_name_scrubbed():
    assert scrub_pii("I met John Smith yesterday").scrubbed_text == "I met [Person A] yesterday"


def test_two_distinct_people_get_distinct_aliases():
    result = scrub_pii("John Smith met Jane Doe")
    assert result.scrubbed_text == "[Person A] met [Person B]"


def test_same_person_alias_is_stable_within_call():
    result = scrub_pii("John Smith said John Smith agreed")
    assert result.scrubbed_text == "[Person A] said [Person A] agreed"


def test_salary_bucketed():
    assert scrub_pii("Salary was 185k").scrubbed_text == "Salary was [Salary 180-200k]"


def test_bare_numeric_range_not_treated_as_salary():
    # "100-150" has no k/000 magnitude marker — it is ambiguous (counts, scores,
    # page ranges) and must not be redacted as salary.
    assert scrub_pii("專案 100-150 小時").scrubbed_text == "專案 100-150 小時"
    assert "salary" not in detect_pii("we ran 100-150 experiments")


def test_age_bucketed():
    assert scrub_pii("She is 34 years old").scrubbed_text == "She is [Age 30s]"


def test_taiwan_id_scrubbed():
    result = scrub_pii("A123456789")
    assert result.scrubbed_text == "[TW_ID]"
    assert result.redactions[0].category == "tw_id"


def test_fragmented_emoji_name_is_documented_gap():
    result = scrub_pii("John 🤖 Smith joined")
    assert result.scrubbed_text == "John 🤖 Smith joined"
    assert result.redactions == []


def test_empty_short_and_whitespace_inputs_do_not_crash():
    assert scrub_pii("").redactions == []
    assert scrub_pii("x").scrubbed_text == "x"
    assert scrub_pii("   ").scrubbed_text == "   "


def test_existing_placeholder_is_idempotent():
    result = scrub_pii("[Person A] met John Smith")
    assert result.scrubbed_text == "[Person A] met [Person A]"
    assert len(result.redactions) == 1


def test_over_redaction_guard_falls_back_to_original(caplog):
    caplog.set_level(logging.WARNING)
    text = "John Smith 0912-345-678 maki@example.com"
    result = scrub_pii(text)
    assert result.scrubbed_text == text
    assert result.redactions == []
    assert "exceeded 50 percent" in caplog.text
