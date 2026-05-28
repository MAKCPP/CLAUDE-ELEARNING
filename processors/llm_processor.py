import json
import re


CLAUDE_MODELS = {
    "claude-opus-4-7": "Claude Opus 4.7 (le plus puissant)",
    "claude-sonnet-4-6": "Claude Sonnet 4.6 (recommandé)",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5 (rapide)",
    "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
    "claude-3-5-haiku-20241022": "Claude 3.5 Haiku",
}

OPENAI_MODELS = {
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o Mini (rapide)",
    "gpt-4-turbo": "GPT-4 Turbo",
}

# OpenRouter — clé sk-or-v1-... — https://openrouter.ai
OPENROUTER_MODELS = {
    "openai/gpt-4o": "OpenRouter · GPT-4o",
    "openai/gpt-4o-mini": "OpenRouter · GPT-4o Mini (rapide)",
    "anthropic/claude-3.5-sonnet": "OpenRouter · Claude 3.5 Sonnet",
    "anthropic/claude-3-haiku": "OpenRouter · Claude 3 Haiku (rapide)",
    "google/gemini-2.0-flash-001": "OpenRouter · Gemini 2.0 Flash",
    "google/gemini-flash-1.5": "OpenRouter · Gemini 1.5 Flash",
    "meta-llama/llama-3.3-70b-instruct": "OpenRouter · Llama 3.3 70B",
    "mistralai/mistral-large": "OpenRouter · Mistral Large",
    "qwen/qwen-2.5-72b-instruct": "OpenRouter · Qwen 2.5 72B",
    "deepseek/deepseek-chat-v3-0324": "OpenRouter · DeepSeek V3",
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

ALL_MODELS = {**CLAUDE_MODELS, **OPENAI_MODELS, **OPENROUTER_MODELS}


def segment_text_by_slides(
    narration_text: str,
    slide_infos: list[dict],
    llm_model: str,
    api_key: str,
) -> list[str]:
    """Ask the LLM to split the narration into one segment per slide.

    Returns a list of text strings, one per slide, in order.
    Falls back to equal proportional splitting if the LLM fails.
    """
    n = len(slide_infos)
    slides_desc = "\n".join(
        f"Slide {s['slide_number']}: «{s['title']}» — {s['content'][:300]}"
        for s in slide_infos
    )

    prompt = f"""Tu es un expert en création de contenu e-learning.

J'ai une présentation PowerPoint de {n} slides et un texte de narration complet.
Ta tâche est de diviser le texte de narration en exactement {n} segments consécutifs, un par slide.

Voici les slides :
{slides_desc}

Voici le texte de narration complet :
\"\"\"
{narration_text}
\"\"\"

Règles importantes :
- Les segments doivent être des parties consécutives du texte original (ne modifie pas le texte).
- Chaque segment doit correspondre thématiquement à son slide.
- Le texte doit être intégralement couvert (pas de partie omise, pas de doublon).
- Retourne un objet JSON strictement valide avec cette structure :
{{
  "segments": [
    {{"slide": 1, "text": "texte du segment 1..."}},
    {{"slide": 2, "text": "texte du segment 2..."}},
    ...
  ]
}}

Ne retourne QUE le JSON, sans texte autour."""

    raw = _call_llm(prompt, llm_model, api_key)
    segments = _parse_segments(raw, n)

    if segments:
        return segments

    # Fallback: equal split by sentences
    return _equal_split(narration_text, n)


def _call_llm(prompt: str, model: str, api_key: str) -> str:
    if model in CLAUDE_MODELS:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    if model in OPENROUTER_MODELS:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    # Native OpenAI
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _parse_segments(raw: str, expected: int) -> list[str] | None:
    """Extract the segments array from LLM output."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"```\s*$", "", raw.strip(), flags=re.MULTILINE)

    try:
        data = json.loads(raw)
        segs = data.get("segments", [])
        if len(segs) == expected:
            return [s["text"] for s in sorted(segs, key=lambda x: x["slide"])]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def _equal_split(text: str, n: int) -> list[str]:
    """Split text into n roughly equal parts by sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if not sentences:
        return [text] * n

    chunk_size = max(1, len(sentences) // n)
    parts = []
    for i in range(n):
        start = i * chunk_size
        end = start + chunk_size if i < n - 1 else len(sentences)
        parts.append(" ".join(sentences[start:end]))
    return parts
