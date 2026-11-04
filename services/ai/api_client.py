"""Bring-your-own-key AI: any OpenAI-compatible chat API (OpenAI, Groq, OpenRouter, Gemini...).

The project ships no key. The person running the app sets AI_API_URL, AI_API_KEY and
AI_API_MODEL in their own .env file. The key is only ever sent to AI_API_URL.
"""
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from services.ai.errors import AiError

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Following a redirect would send the key to whatever host the reply names."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def base_url() -> str:
    return os.getenv("AI_API_URL", "").strip().rstrip("/")


def model() -> str:
    return os.getenv("AI_API_MODEL", "").strip()


def host() -> str:
    return urlparse(base_url()).hostname or ""


def config_problem() -> Optional[str]:
    """What is wrong with the settings, in plain words, or None."""
    missing = [name for name in ("AI_API_URL", "AI_API_KEY", "AI_API_MODEL") if not os.getenv(name, "").strip()]
    if missing:
        return f"Add {', '.join(missing)} to your .env file and restart the app."
    parsed = urlparse(base_url())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "AI_API_URL must be a full address, such as https://api.openai.com/v1"
    if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS:
        return "AI_API_URL must use https, so your key is not sent in plain text."
    return None


def _content(reply: Dict[str, Any]) -> Dict[str, Any]:
    try:
        text = reply["choices"][0]["message"]["content"]
        # Some models wrap JSON in a Markdown code fence.
        text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text)
        return json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise AiError("The AI reply was not valid JSON") from e


def complete(messages: List[Dict[str, str]], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Ask for JSON matching ``schema``. Not every provider enforces a schema, so it is also in the prompt."""
    problem = config_problem()
    if problem:
        raise AiError(problem)
    instruction = {"role": "system", "content": "Reply with one JSON object matching this JSON schema: "
                                                + json.dumps(schema)}
    payload = {"model": model(), "messages": [*messages, instruction], "temperature": 0,
               "response_format": {"type": "json_object"}}
    request = urllib.request.Request(
        base_url() + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['AI_API_KEY'].strip()}"})
    try:
        with _opener.open(request, timeout=float(os.getenv("AI_API_TIMEOUT", "60"))) as response:
            reply = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        hint = {401: " (check AI_API_KEY)", 403: " (check AI_API_KEY)", 404: " (check AI_API_URL and AI_API_MODEL)",
                429: " (limit or credit used up)"}.get(e.code, "")
        raise AiError(f"The AI API returned HTTP {e.code}{hint}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AiError("The AI API is not reachable") from None
    except ValueError:
        raise AiError("The AI API sent an unreadable reply") from None
    return _content(reply)
