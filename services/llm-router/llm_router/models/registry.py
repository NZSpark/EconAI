"""Model registry with hot-reload from YAML config."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from llm_router.models.schemas import ModelInfo

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Maintains the list of available LLM models, loaded from a YAML config file.

    Supports hot-reload: call reload() to refresh from disk without restarting.
    """

    def __init__(self, config_path: str | Path) -> None:
        self._config_path = Path(config_path)
        self._models: dict[str, ModelInfo] = {}
        self._default_local: str = ""
        self._default_cloud: str = ""
        self._load()

    def _load(self) -> None:
        """Load model configuration from the YAML file."""
        try:
            with open(self._config_path) as f:
                data: dict[str, Any] = yaml.safe_load(f)

            self._default_local = data.get("default_local", "")
            self._default_cloud = data.get("default_cloud", "")

            models: list[ModelInfo] = []
            for m in data.get("models", []):
                models.append(
                    ModelInfo(
                        id=m["id"],
                        provider=m.get("provider", ""),
                        type=m.get("type", ""),
                        description=m.get("description", ""),
                        capabilities=m.get("capabilities", []),
                    )
                )

            self._models = {m.id: m for m in models}
            logger.info("Model registry loaded: %d models", len(self._models))
        except Exception:
            logger.exception("Failed to load model registry from %s", self._config_path)
            if not self._models:
                self._init_defaults()

    def _init_defaults(self) -> None:
        """初始化 a minimal default registry for fallback."""
        defaults = [
            ModelInfo(id="auto", provider="auto", type="auto", description="auto-routing"),
            ModelInfo(id="claude-sonnet-4-6", provider="anthropic", type="cloud", description="Claude Sonnet 4.6"),
            ModelInfo(id="local:qwen3-72b", provider="vllm", type="local", description="Qwen3 72B"),
        ]
        self._models = {m.id: m for m in defaults}
        self._default_local = "local:qwen3-72b"
        self._default_cloud = "claude-sonnet-4-6"

    def reload(self) -> None:
        """Hot-reload the model configuration from disk."""
        logger.info("Reloading model registry...")
        self._load()

    def get_model(self, model_id: str) -> ModelInfo | None:
        """获取 a model by its ID."""
        return self._models.get(model_id)

    def list_models(self) -> list[ModelInfo]:
        """列出 all registered models."""
        return list(self._models.values())

    @property
    def default_local(self) -> str:
        return self._default_local

    @property
    def default_cloud(self) -> str:
        return self._default_cloud

    def get_models_by_type(self, model_type: str) -> list[ModelInfo]:
        """Filter models by type (cloud/local/auto)."""
        return [m for m in self._models.values() if m.type == model_type]

    def get_cloud_models(self) -> list[ModelInfo]:
        """获取 all cloud models."""
        return self.get_models_by_type("cloud")

    def get_local_models(self) -> list[ModelInfo]:
        """获取 all local models."""
        return self.get_models_by_type("local")

    def has_model(self, model_id: str) -> bool:
        """检查 if a model ID is registered."""
        return model_id in self._models
