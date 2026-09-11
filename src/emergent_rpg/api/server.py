from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from emergent_rpg.api.app import create_app
from emergent_rpg.providers.errors import ProviderConfigurationError
from emergent_rpg.providers.factory import ActionParserName, NarrativeProviderName


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the emergent-rpg-engine Web API.")
    parser.add_argument("--db", type=Path, default=Path("emergent-rpg.db"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--provider",
        choices=[item.value for item in NarrativeProviderName],
        default=NarrativeProviderName.SCRIPTED.value,
    )
    parser.add_argument(
        "--action-parser",
        choices=[item.value for item in ActionParserName],
        default=ActionParserName.DETERMINISTIC.value,
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65_535:
        parser.error("--port must be between 1 and 65535")

    try:
        app = create_app(
            db_path=args.db,
            narrative_provider=args.provider,
            action_parser=args.action_parser,
        )
    except ProviderConfigurationError as exc:
        parser.error(str(exc))
        raise AssertionError("unreachable") from exc

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
