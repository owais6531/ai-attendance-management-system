"""Chooses the AI backend. AI_PROVIDER: ollama (default, local), api (your own key) or off."""
import os
from typing import Any, Dict, List
from urllib.parse import urlparse

from services.ai import api_client, ollama_client
from services.ai.errors import AiError


def name() -> str:
    value = os.getenv("AI_PROVIDER", "ollama").strip().lower()
    return value if value in ("ollama", "api", "off") else "ollama"


def model_name() -> str:
    chosen = name()
    if chosen == "api":
        return api_client.model() or "not set"
    return ollama_client.text_model() if chosen == "ollama" else "off"


def status() -> Dict[str, Any]:
    chosen = name()
    if chosen == "off":
        return {"provider": "off", "available": False, "model": "off", "external": False, "host": None,
                "hint": "AI suggestions are turned off (AI_PROVIDER=off)."}
    if chosen == "api":
        problem = api_client.config_problem()
        host = api_client.host() or None
        return {"provider": "api", "available": problem is None, "model": model_name(), "hint": problem,
                "external": host not in api_client.LOCAL_HOSTS, "host": host}
    host = urlparse(ollama_client.base_url()).hostname
    return {"provider": "ollama", **ollama_client.status(), "external": host not in api_client.LOCAL_HOSTS,
            "host": host}


def complete(messages: List[Dict[str, str]], schema: Dict[str, Any]) -> Dict[str, Any]:
    chosen = name()
    if chosen == "api":
        return api_client.complete(messages, schema)
    if chosen == "ollama":
        return ollama_client.complete(messages, schema)
    raise AiError("AI suggestions are turned off")
