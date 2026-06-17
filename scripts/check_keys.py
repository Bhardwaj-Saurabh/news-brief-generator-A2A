"""Report which required environment variables are present in .env — never their values.

Run: ``uv run python scripts/check_keys.py``

Prints a ✅/❌ line per variable and exits 0 only when every required variable is set
to a non-empty value. Values are NEVER printed (presence/absence only), so this is safe
to paste into an issue or CI log.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Required variables grouped by purpose. The actual SECRETS (api keys / endpoint) and the
# required non-secret config (deployment, api version) are all checked the same way:
# we only ever read presence, never the value.
REQUIRED: dict[str, list[str]] = {
    "Upstream API keys": [
        "NEWSAPI_KEY",          # News / World Data -> NewsAPI.org
        "OPENWEATHER_API_KEY",  # Weather           -> OpenWeatherMap
        "FINNHUB_API_KEY",      # Finance           -> Finnhub
        "YOUTUBE_API_KEY",      # Media             -> YouTube Data API v3
    ],
    "Azure OpenAI (Publisher LLM)": [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    ],
}


def main() -> int:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    loaded = load_dotenv(env_path)
    print(f".env loaded from {env_path}" if loaded else f"no .env at {env_path}; checking process env")
    print()

    missing: list[str] = []
    for group, names in REQUIRED.items():
        print(f"{group}:")
        for name in names:
            present = bool(os.environ.get(name, "").strip())
            print(f"  {'✅' if present else '❌'} {name:<30} {'present' if present else 'MISSING'}")
            if not present:
                missing.append(name)
        print()

    if missing:
        print(f"{len(missing)} missing: {', '.join(missing)}")
        return 1
    print("All required variables present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
