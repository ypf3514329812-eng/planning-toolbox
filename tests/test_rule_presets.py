"""Tests for the user-facing planning-condition template module."""

import pytest
import sys

from planning_toolbox.cli import main
from planning_toolbox.rules.presets import (
    RulePreset,
    get_rule_preset,
    list_rule_presets,
)
from planning_toolbox.rules.standards import get_standards_profile, list_standards_profiles
from planning_toolbox.rules.drafting import (
    get_drafting_profile,
    get_drafting_reference,
    list_drafting_profiles,
)


def test_builtin_rule_presets_are_explicit_and_stable():
    presets = list_rule_presets()
    assert [preset.preset_id for preset in presets] == ["custom", "learning_example"]

    learning = get_rule_preset("learning_example")
    assert learning.floors == 6
    assert learning.setback_m == pytest.approx(5.0)
    assert "不代表法定规范" in learning.name
    assert learning.to_task_params()["building_layer"] == "BUILDING"


def test_rule_preset_rejects_invalid_values():
    with pytest.raises(ValueError):
        RulePreset("bad", "错误模板", "", floors=0, setback_m=5.0)
    with pytest.raises(ValueError):
        RulePreset("bad", "错误模板", "", floors=6, setback_m=-1.0)


def test_standards_profiles_are_explicit_reference_frameworks():
    profiles = list_standards_profiles()
    assert [profile.profile_id for profile in profiles] == [
        "custom_local",
        "residential_national_framework",
        "civil_building_national_framework",
    ]
    residential = get_standards_profile("residential_national_framework")
    assert "GB 50180-2018" in residential.reference_codes
    assert "地方规划条件" in residential.description or "地方" in residential.description


def test_cli_lists_rule_presets(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "planning-toolbox", "rules", "list"
    ])
    main()
    captured = capsys.readouterr()
    assert "learning_example" in captured.out
    assert "custom" in captured.out


def test_chinese_drafting_profiles_are_scoped_and_traceable():
    profiles = list_drafting_profiles()
    assert [profile.profile_id for profile in profiles] == [
        "china_coursework_general",
        "china_residential_site",
        "china_territorial_spatial_review",
    ]
    coursework = get_drafting_profile("china_coursework_general")
    territorial = get_drafting_profile("china_territorial_spatial_review")
    assert "PARCEL" in coursework.required_layers
    assert territorial.require_projected_crs_review is True
    reference = get_drafting_reference("GB/T 20257.1-2017")
    assert "2025" in reference.status
    assert reference.source_url.startswith("https://")
