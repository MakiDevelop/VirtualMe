from virtualme.evals.__main__ import main
from virtualme.evals.harness import load_fixtures, render_scorecard, run_eval


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self, texts: list[str]):
        self.texts = texts
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"content": [_Content(self.texts.pop(0))]})


class _Claude:
    def __init__(self, texts: list[str]):
        self.messages = _Messages(texts)


def test_load_fixtures_reads_packaged_yaml():
    cases = load_fixtures()

    assert cases
    for case in cases:
        assert {"id", "question", "answer", "expected_depth", "expected_rule"} <= set(case)
        assert case["expected_depth"] in {"fact", "pattern", "principle"}
        assert case["expected_rule"] in {"R1", "R2", "R3", "R4", None}


async def test_run_eval_without_llm_scores_rules_only():
    report = await run_eval(load_fixtures(), claude=None)

    assert report.rule_accuracy == 1.0
    assert report.depth_accuracy is None
    assert report.with_llm is False
    assert all(result.depth_actual is None for result in report.results)
    assert all(result.depth_ok is None for result in report.results)


async def test_render_scorecard_contains_summary():
    report = await run_eval(load_fixtures(), claude=None)

    markdown = render_scorecard(report)

    assert "# Engine Evaluation Scorecard" in markdown
    assert "Rule accuracy: 100.0%" in markdown
    assert "| ID | Depth Expected | Depth Actual | Rule Expected | Rule Actual | Pass |" in markdown


async def test_evals_cli_writes_scorecard_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(
        "sys.argv",
        [
            "virtualme.evals",
            "--out",
            str(tmp_path / "evals"),
        ],
    )

    await main()

    scorecard = tmp_path / "evals" / "scorecard.md"
    assert scorecard.exists()
    assert "Rule accuracy: 100.0%" in scorecard.read_text(encoding="utf-8")


async def test_run_eval_with_mock_claude_scores_depth():
    cases = load_fixtures()[:3]
    claude = _Claude([case["expected_depth"] for case in cases])

    report = await run_eval(cases, claude=claude)

    assert report.with_llm is True
    assert report.depth_accuracy == 1.0
    assert [result.depth_actual for result in report.results] == [
        case["expected_depth"] for case in cases
    ]
    assert all(result.depth_ok is True for result in report.results)
