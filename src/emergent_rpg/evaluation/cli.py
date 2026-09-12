from __future__ import annotations

import argparse
from pathlib import Path

from emergent_rpg.evaluation.autonomy import run_autonomy_integration_evaluation
from emergent_rpg.evaluation.harness import DEFAULT_SEED, run_consistency_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic consistency and integration evaluations.",
    )
    parser.add_argument("--db", type=Path, default=Path("emergent-rpg-eval.db"))
    parser.add_argument("--scenario", choices=("mixed", "autonomy"), default="mixed")
    parser.add_argument("--turns", type=int, default=1_000)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--checkpoint-interval", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.turns < 1:
        parser.error("--turns must be positive")
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    if args.checkpoint_interval < 1:
        parser.error("--checkpoint-interval must be positive")

    try:
        if args.scenario == "autonomy":
            report = run_autonomy_integration_evaluation(
                args.db,
                rounds=args.rounds,
            )
        else:
            report = run_consistency_evaluation(
                args.db,
                turns=args.turns,
                seed=args.seed,
                checkpoint_interval=args.checkpoint_interval,
            )
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))
        raise AssertionError("unreachable") from exc

    payload = report.model_dump_json(indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
