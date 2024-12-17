"""Utils to help with LLM setup."""

from __future__ import annotations

import os

from .llm_config import LlmConfig
from .llm_providers import LlmProvider, provider_base_urls, provider_default_models, provider_env_key_names


def llm_config_from_env(prefix: str = "PARAI") -> LlmConfig:
    """
    Create instance of LlmConfig from environment variables.
    The following environment variables are used:

    - {prefix}_AI_PROVIDER (required)
    - {prefix}_MODEL (optional - defaults to provider default)
    - {prefix}_AI_BASE_URL (optional - defaults to provider default)
    - {prefix}_TEMPERATURE (optional - defaults to 0.8)
    - {prefix}_USER_AGENT_APPID (optional)
    - {prefix}_STREAMING (optional - defaults to false)
    - {prefix}_MAX_CONTEXT_SIZE (optional - defaults to provider default)

    Args:
        prefix: Prefix to use for environment variables (default: "PARAI")

    Returns:
        LlmConfig
    """
    prefix = prefix.strip("_")
    ai_provider_name = os.environ.get(f"{prefix}_AI_PROVIDER")
    if not ai_provider_name:
        raise ValueError(f"{prefix}_AI_PROVIDER environment variable not set.")

    ai_provider = LlmProvider(ai_provider_name)
    if ai_provider not in [LlmProvider.OLLAMA, LlmProvider.BEDROCK]:
        key_name = provider_env_key_names[ai_provider]
        if not os.environ.get(key_name):
            raise ValueError(f"{key_name} environment variable not set.")

    model_name = os.environ.get(f"{prefix}_MODEL") or provider_default_models[ai_provider]
    if not model_name:
        raise ValueError(f"{prefix}_MODEL environment variable not set.")

    ai_base_url = os.environ.get(f"{prefix}_AI_BASE_URL") or provider_base_urls[ai_provider]
    temperature = float(os.environ.get(f"{prefix}_TEMPERATURE", 0.8))
    user_agent_appid = os.environ.get(f"{prefix}_USER_AGENT_APPID")
    streaming = os.environ.get(f"{prefix}_STREAMING", "false") == "true"
    max_context_size = int(os.environ.get(f"{prefix}_MAX_CONTEXT_SIZE", 0))

    return LlmConfig(
        provider=ai_provider,
        model_name=model_name,
        base_url=ai_base_url,
        temperature=temperature,
        user_agent_appid=user_agent_appid,
        streaming=streaming,
        num_ctx=max_context_size,
        env_prefix=prefix,
    )
