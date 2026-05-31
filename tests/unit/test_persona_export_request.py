from datetime import datetime
from zoneinfo import ZoneInfo

from virtualme.export.persona_package import render_export_note
from virtualme.interview.progress_card import (
    calculate_weighted_completion,
    render_8x3_progress_card,
)
from virtualme.interview.turn_state import (
    CoverageSnapshot,
    DimensionProgress,
    LayerProgress,
)
from virtualme.storage.db import Dimension, Layer


def _snapshot(score: float) -> CoverageSnapshot:
    return CoverageSnapshot(
        per_dimension={
            dimension: DimensionProgress(
                dimension=dimension,
                layers={
                    Layer.FACT: LayerProgress(quality_score=score),
                    Layer.PATTERN: LayerProgress(quality_score=score),
                    Layer.PRINCIPLE: LayerProgress(quality_score=score),
                },
            )
            for dimension in Dimension
        }
    )


def test_weighted_completion_boundaries():
    assert calculate_weighted_completion(CoverageSnapshot()) == 0
    assert calculate_weighted_completion(_snapshot(0.0)) == 0
    assert calculate_weighted_completion(_snapshot(1.0)) == 100


def test_weighted_completion_applies_deep_middle_shallow_weights():
    snapshot = CoverageSnapshot(
        per_dimension={
            dimension: DimensionProgress(
                dimension=dimension,
                layers={
                    Layer.FACT: LayerProgress(quality_score=1.0),
                    Layer.PATTERN: LayerProgress(quality_score=0.0),
                    Layer.PRINCIPLE: LayerProgress(quality_score=1.0),
                },
            )
            for dimension in Dimension
        }
    )

    assert calculate_weighted_completion(snapshot) == 65


def test_progress_card_header_and_layers():
    card = render_8x3_progress_card(_snapshot(0.8))

    assert card.startswith("VirtualMe 訪談機器人 【目前訪談收集進度（八維 × 三層）】")  # noqa: RUF001
    assert "聲音/表達" in card
    assert "淺層:●●●  中層:●●●  深層:●●●" in card


def test_export_note_contains_required_sections():
    note = render_export_note(_snapshot(0.0), datetime(2026, 5, 20, tzinfo=ZoneInfo("Asia/Taipei")))

    assert "匯出時間" in note
    assert "目前 8 維 × 3 層覆蓋情況" in note  # noqa: RUF001
    assert "較弱維度提醒" in note
    assert "這是階段性版本，隨著訪談繼續會越來越成熟" in note  # noqa: RUF001
