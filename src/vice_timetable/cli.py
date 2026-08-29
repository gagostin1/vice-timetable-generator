import argparse

from vice_timetable.generator import (
    add_generate_arguments,
    run_generate,
)
from vice_timetable.representative_day import (
    add_pick_day_arguments,
    run_pick_day,
)


def main():
    parser = argparse.ArgumentParser(
        prog="vice-timetable",
        description="Generate and analyze VICE traffic timetables.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a VICE timetable.",
    )
    add_generate_arguments(generate_parser)

    pick_day_parser = subparsers.add_parser(
        "pick-day",
        help="Find a representative traffic day.",
    )
    add_pick_day_arguments(pick_day_parser)

    args = parser.parse_args()

    if args.command == "generate":
        run_generate(args)
    elif args.command == "pick-day":
        run_pick_day(args)


if __name__ == "__main__":
    main()
