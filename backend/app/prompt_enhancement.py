from __future__ import annotations

from enum import StrEnum


class CreativityPreset(StrEnum):
    FAITHFUL = "faithful"
    BALANCED = "balanced"
    IMAGINATIVE = "imaginative"


DEFAULT_CREATIVITY_PRESET = CreativityPreset.BALANCED
PROVIDER_PROMPT_COMPONENT_KEY = "provider_prompt_en"
PROVIDER_PROMPT_PARAMETER_KEY = "provider_prompt"

CREATIVITY_TEMPERATURES: dict[CreativityPreset, float] = {
    CreativityPreset.FAITHFUL: 0.2,
    CreativityPreset.BALANCED: 0.5,
    CreativityPreset.IMAGINATIVE: 0.8,
}

CREATIVITY_STRATEGIES: dict[CreativityPreset, str] = {
    CreativityPreset.FAITHFUL: (
        "Creativity strategy: Faithful. Stay very close to the user's wording, "
        "avoid generic stock-photo phrasing, and clarify only what is implied."
    ),
    CreativityPreset.BALANCED: (
        "Creativity strategy: Balanced. Preserve the user's intent, avoid "
        "generic stock-photo phrasing, and introduce one distinctive visual idea."
    ),
    CreativityPreset.IMAGINATIVE: (
        "Creativity strategy: Imaginative. Keep the user's core nouns and verbs, "
        "avoid generic stock-photo phrasing, and add richer visual specificity "
        "with one distinctive visual idea."
    ),
}


def normalize_creativity_preset(
    value: CreativityPreset | str | None,
) -> CreativityPreset:
    if value is None:
        return DEFAULT_CREATIVITY_PRESET
    if isinstance(value, CreativityPreset):
        return value
    return CreativityPreset(value)


def temperature_for_preset(preset: CreativityPreset) -> float:
    return CREATIVITY_TEMPERATURES[preset]


def strategy_for_preset(preset: CreativityPreset) -> str:
    return CREATIVITY_STRATEGIES[preset]
