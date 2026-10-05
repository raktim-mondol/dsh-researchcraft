"""Model backends for the verifier. The engine never handles API keys.

`pi`      runs your Pi installation headlessly with no tools, so it uses whatever provider you configured.
`http`    OpenAI-compatible HTTP (Ollama, llama.cpp, vLLM). Local URLs satisfy `data_policy: local`.
`command` runs any program that reads the prompt on stdin and prints the reply.
`fake`    for tests.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse


@dataclass
class Completion:
    text: str = ""
    usage: dict = field(default_factory=dict)
    error: str | None = None


class Backend:
    name = "base"
    model = "none"

    def complete(self, prompt: str) -> Completion:  # pragma: no cover
        raise NotImplementedError


class PiBackend(Backend):
    name = "pi"

    def __init__(self, provider: str, model: str, timeout: int = 150, retries: int = 1, thinking: str = "off"):
        self.provider, self.model, self.timeout, self.retries, self.thinking = provider, model, timeout, retries, thinking

    def complete(self, prompt: str) -> Completion:
        cmd = ["pi", "-p", "--mode", "json", "--no-session", "--no-tools", "--no-context-files", "--no-skills",
               "--no-extensions", "--no-prompt-templates", "--offline", "--provider", self.provider, "--model", self.model]
        if self.thinking:                       # some models reject "off"; an empty setting sends no flag
            cmd += ["--thinking", self.thinking]
        cmd.append(prompt)
        last = "unknown error"
        for _ in range(self.retries + 1):
            try:
                with tempfile.TemporaryDirectory() as cwd:      # nothing for the model to find in cwd
                    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                last = f"timeout after {self.timeout}s"
                continue
            except OSError as e:
                return Completion(error=f"cannot run pi: {e}")
            text, usage = "", {}
            for line in p.stdout.splitlines():
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "message_end" and d.get("message", {}).get("role") == "assistant":
                    m = d["message"]
                    t = "".join(b.get("text", "") for b in m.get("content", []) if b.get("type") == "text")
                    if t.strip():
                        text = t
                    u = m.get("usage") or {}
                    usage = {"input": u.get("input", 0), "output": u.get("output", 0)}
                    if m.get("stopReason") == "error":
                        last = str(m.get("errorMessage") or "provider error")[:200]
            if text.strip():
                return Completion(text, usage)
            last = last if last != "unknown error" else (p.stderr.strip()[-200:] or "empty reply")
        return Completion(error=last)


class CommandBackend(Backend):
    name = "command"

    def __init__(self, cmd: list[str], timeout: int = 150):
        self.cmd, self.timeout, self.model = cmd, timeout, " ".join(cmd)[:60]

    def complete(self, prompt: str) -> Completion:
        try:
            p = subprocess.run(self.cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            return Completion(error=str(e))
        return Completion(p.stdout) if p.returncode == 0 and p.stdout.strip() else Completion(error=p.stderr.strip()[-200:] or "empty reply")


class PolicyError(ValueError):
    """Raised when the configured backend is forbidden by `data_policy`."""


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def endpoint_class(backend_name: str, url: str | None = None) -> str:
    """'local' (stays on the machine) or 'remote' (a hosted API)."""
    if backend_name in ("command", "fake"):
        return "local"
    if backend_name == "http" and url:
        host = (urlparse(url).hostname or "").lower()
        return "local" if host in LOCAL_HOSTS else "remote"
    return "remote"


def admit(cfg: dict, backend_name: str, url: str | None = None) -> None:
    """Refuse a backend that the project's data_policy does not allow (design 13.3)."""
    policy = str(cfg.get("data_policy") or "open").lower()
    klass = endpoint_class(backend_name, url)
    if policy == "open":
        return
    if policy == "local" and klass != "local":
        raise PolicyError(f"data_policy=local forbids remote backend '{backend_name}'"
                          + (f" ({url})" if url else "") + "; use backend: http with a 127.0.0.1 URL, or backend: command")
    if policy == "restricted":
        if klass == "local":
            return
        allow = [str(x).lower() for x in (cfg.get("data_policy_allow") or [])]
        provider = str((cfg.get("verifier") or {}).get("provider") or backend_name).lower()
        if provider not in allow and backend_name.lower() not in allow:
            raise PolicyError(f"data_policy=restricted forbids '{provider}' ({backend_name}); allow it in data_policy_allow")


class HttpBackend(Backend):
    """OpenAI-compatible chat completions. Point `verifier.url` at Ollama (`http://127.0.0.1:11434/v1`)
    or llama.cpp / vLLM. The API key, if any, comes from the environment (never from the project)."""
    name = "http"

    def __init__(self, url: str, model: str, timeout: int = 150, api_key_env: str = "AH_VERIFIER_API_KEY"):
        self.url, self.model, self.timeout, self.api_key_env = url.rstrip("/"), model, timeout, api_key_env

    def complete(self, prompt: str) -> Completion:
        base = self.url
        if not base.endswith("/chat/completions"):
            base = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
        body = json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt}],
                           "temperature": 0}).encode()
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env, "")
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(base, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                d = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            return Completion(error=str(e)[:200])
        text = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        u = d.get("usage") or {}
        usage = {"input": u.get("prompt_tokens") or u.get("input", 0), "output": u.get("completion_tokens") or u.get("output", 0)}
        return Completion(text, usage) if text.strip() else Completion(error="empty reply")


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, fn: Callable[[str], str], model: str = "fake-1"):
        self.fn, self.model, self.calls = fn, model, 0

    def complete(self, prompt: str) -> Completion:
        self.calls += 1
        return Completion(self.fn(prompt))


def get_backend(cfg: dict) -> Backend | None:
    v = cfg.get("verifier") or {}
    kind = v.get("backend")
    if kind == "pi":
        admit(cfg, "pi")
        return PiBackend(v["provider"], v["model"], int(v.get("timeout", 150)), int(v.get("retries", 1)), v.get("thinking", "off"))
    if kind == "http":
        url = v.get("url") or v.get("base_url") or ""
        if not url:
            raise PolicyError("verifier.backend=http needs verifier.url (e.g. http://127.0.0.1:11434/v1)")
        admit(cfg, "http", url)
        return HttpBackend(url, v["model"], int(v.get("timeout", 150)), v.get("api_key_env", "AH_VERIFIER_API_KEY"))
    if kind == "command":
        admit(cfg, "command")
        return CommandBackend(list(v["cmd"]), int(v.get("timeout", 150)))
    return None
