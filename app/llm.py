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
    resp = client.beta.messages.create(
        model=cfg.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise LLMUnavailable("Model odmówił odpowiedzi")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise LLMUnavailable("Pusta odpowiedź modelu")
    usage = {"model": resp.model, "input_tokens": resp.usage.input_tokens,
             "output_tokens": resp.usage.output_tokens}
    return text, usage
