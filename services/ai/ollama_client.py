"""Small client for a local Ollama server. Free, no API keys, nothing leaves the machine.

The rest of the app works normally when Ollama is off; every call here fails with
OllamaError, which callers turn into a friendly message.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

from services.ai.errors import AiError

logger = logging.getLogger(__name__)
DEFAULT_URL = "http://localhost:11434"
DEFAULT_TEXT_MODEL = "llama3.2:3b"

# Local requests must not go through a corporate proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaError(AiError):
    pass


def base_url() -> str:
    return os.getenv("OLLAMA_URL", DEFAULT_URL).rstrip("/")


def text_model() -> str:
    return os.getenv("OLLAMA_TEXT_MODEL", DEFAULT_TEXT_MODEL)


def _request(path: str, payload: Dict[str, Any] | None, timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(base_url() + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with _opener.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise OllamaError(f"Ollama returned HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OllamaError("Ollama is not reachable") from e
    except ValueError as e:
        raise OllamaError("Ollama sent an unreadable reply") from e


def status() -> Dict[str, Any]:
    """Is Ollama running and is the configured model installed?"""
    model = text_model()
    try:
        tags = _request("/api/tags", None, timeout=2)
    except OllamaError:
        return {"available": False, "running": False, "model": model,
                "hint": "AI is optional and off. To use it, install Ollama from ollama.com or add your own API key: see AI options."}
    names = [m.get("name", "") for m in tags.get("models", [])]
    ready = model in names or f"{model}:latest" in names
    return {"available": ready, "running": True, "model": model,
            "hint": None if ready else f"Ollama is running. Install the model with: ollama pull {model}"}


def complete(messages: List[Dict[str, str]], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Ask the model for JSON matching ``schema``. Returns the parsed object."""
    payload = {"model": text_model(), "messages": messages, "format": schema, "stream": False,
               "options": {"temperature": 0}}
    reply = _request("/api/chat", payload, timeout=float(os.getenv("OLLAMA_TIMEOUT", "120")))
    try:
        return json.loads(reply["message"]["content"])
    except (KeyError, TypeError, ValueError) as e:
        raise OllamaError("The AI reply was not valid JSON") from e
