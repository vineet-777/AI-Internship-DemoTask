"""Seed a deterministic starter set for future startup entity resolution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

KNOWN_AI_STARTUPS = (
    "Anthropic", "OpenAI", "Cohere", "Hugging Face", "Mistral AI", "Perplexity", "Scale AI",
    "Databricks", "xAI", "Runway", "Adept", "Character.AI", "Inflection AI", "Stability AI",
    "Midjourney", "ElevenLabs", "Replit", "Cursor", "Harvey", "Glean", "Pika", "Synthesia",
    "Weights & Biases", "Together AI", "Anyscale", "LangChain", "Modal", "Replicate", "Vercel",
    "Pinecone", "Weaviate", "Chroma", "LlamaIndex", "Jasper", "Copy.ai", "Writer", "Sierra",
    "Hebbia", "Contextual AI", "Imbue", "Poolside", "Abridge", "Hippocratic AI", "Nabla",
    "Tempus", "Insilico Medicine", "Wayve", "Covariant", "Physical Intelligence", "Figure AI",
)


def seed_records() -> list[dict[str, str]]:
    return [
        {
            "canonicalEntityId": f"startup:{name.casefold().replace(' ', '-').replace('&', 'and')}",
            "rawEntityName": name,
        }
        for name in KNOWN_AI_STARTUPS
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the 50 known AI startup entity seeds")
    parser.add_argument("--output", type=Path, default=Path("data/normalized/startup_entities.json"))
    args = parser.parse_args()
    if len(KNOWN_AI_STARTUPS) != 50:
        raise RuntimeError("The seed set must contain exactly 50 startups")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seed_records(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
