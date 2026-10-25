"""Claude calls. Without ANTHROPIC_API_KEY the agents use plain templates instead."""
import os

import anthropic


class LLMUnavailable(Exception):
    pass


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def write(cfg, system: str, content: str, *, max_tokens: int = 4000):
    """Return (text, usage dict)."""
    if not available():
        raise LLMUnavailable("Brak ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()
    try:
        resp = _create(client, cfg, system, content, max_tokens)
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
        # The report must still go out; the caller falls back to the template.
        raise LLMUnavailable(f"API niedostępne: {exc.__class__.__name__}") from exc
    if resp.stop_reason == "refusal":
        raise LLMUnavailable("Model odmówił odpowiedzi")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise LLMUnavailable("Pusta odpowiedź modelu")
    usage = {"model": resp.model, "input_tokens": resp.usage.input_tokens,
             "output_tokens": resp.usage.output_tokens}
    return text, usage


def _create(client, cfg, system, content, max_tokens):
    return client.beta.messages.create(
        model=cfg.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
