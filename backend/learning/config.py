"""Validated configuration shared by every AI-backed learning feature."""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
FEATURES = ("summary", "flashcards", "mcq", "chat")
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def _load_features() -> dict[str, dict[str, str | None]]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read learning configuration {CONFIG_PATH}: {exc}") from exc
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, dict):
        raise RuntimeError(f"{CONFIG_PATH} must contain a features object.")
    result = {}
    for feature in FEATURES:
        configured = features.get(feature)
        if not isinstance(configured, dict):
            raise RuntimeError(f"{CONFIG_PATH}: features.{feature} must be an object.")
        model = configured.get("model")
        effort = configured.get("reasoningEffort")
        if not isinstance(model, str) or not model.strip():
            raise RuntimeError(f"{CONFIG_PATH}: features.{feature}.model must be a nonempty model ID.")
        if effort is not None and (not isinstance(effort, str) or effort not in REASONING_EFFORTS):
            raise RuntimeError(f"{CONFIG_PATH}: features.{feature}.reasoningEffort is invalid.")
        model_override = os.environ.get(f"OPENAI_{feature.upper()}_MODEL", "").strip()
        effort_key = f"OPENAI_{feature.upper()}_REASONING_EFFORT"
        has_effort_override = effort_key in os.environ
        effort_override = os.environ.get(effort_key)
        if effort_override is not None:
            effort_override = effort_override.strip() or None
            if effort_override is not None and effort_override not in REASONING_EFFORTS:
                raise RuntimeError(f"OPENAI_{feature.upper()}_REASONING_EFFORT is invalid.")
        result[feature] = {"model": model_override or model.strip(),
                           "reasoningEffort": effort_override if has_effort_override else effort}
    return result


AI_FEATURES = _load_features()
MODELS = {feature: settings["model"] for feature, settings in AI_FEATURES.items()}


def model_for(feature: str) -> str:
    try:
        return AI_FEATURES[feature]["model"]  # type: ignore[return-value]
    except KeyError:
        raise ValueError(f"Unknown learning feature: {feature}") from None


def reasoning_for(feature: str) -> str | None:
    try:
        return AI_FEATURES[feature]["reasoningEffort"]
    except KeyError:
        raise ValueError(f"Unknown learning feature: {feature}") from None
