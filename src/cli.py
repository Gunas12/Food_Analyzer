"""CLI entrypoint.

Usage:
    python -m foodanalyzer analyze <path/to/photo.jpg>

Runs the same FoodAnalyzer pipeline as the HTTP API, prints a totals
table, and exits non-zero on validation errors (so it's script-friendly).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.config import get_settings
from src.core.analyzer import FoodAnalyzer
from src.models import AnalysisRecord
from src.validation import ValidationError
from src.wiring import build_components


def _render(record: AnalysisRecord) -> str:
    if not record.meal_recognized:
        return "Meal not recognized in image."

    lines = [
        f"{'ingredient':<28}{'g':>8}{'kcal':>8}{'protein':>10}{'carbs':>8}{'fat':>8}",
        "-" * 70,
    ]
    for ing in record.ingredients:
        lines.append(
            f"{ing.name:<28}{ing.estimated_grams:>8.0f}{ing.kcal:>8.0f}"
            f"{ing.protein_g:>10.1f}{ing.carbs_g:>8.1f}{ing.fat_g:>8.1f}"
        )
    lines.append("-" * 70)
    lines.append(
        f"TOTAL kcal={record.totals.kcal:.0f} "
        f"protein={record.totals.protein_g:.1f}g "
        f"carbs={record.totals.carbs_g:.1f}g fat={record.totals.fat_g:.1f}g"
    )
    return "\n".join(lines)


async def _run_analyze(image_path: str) -> int:
    settings = get_settings()
    components = build_components(settings)
    await components.repository.init_models()

    analyzer = FoodAnalyzer(
        components.ai_service,
        components.pipeline,
        components.repository,
        max_image_size_mb=settings.max_image_size_mb,
    )

    try:
        record = await analyzer.analyze(image_path)
        print(_render(record))
        return 0
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m foodanalyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_p = sub.add_parser("analyze", help="Analyze one meal photo")
    analyze_p.add_argument("image_path", help="Path to a JPEG/PNG meal photo")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        exit_code = asyncio.run(_run_analyze(args.image_path))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
