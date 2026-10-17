import argparse
from pathlib import Path

from app.db import engine
from app.seed_io import export_seed, load_seed

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="seed/*.json をDBへ投入する")
    seed.add_argument("--dir", type=Path, default=SEED_DIR)

    export = sub.add_parser("export", help="DBの内容をシード形式のJSONへ出力する")
    export.add_argument("-o", "--output", type=Path, default=SEED_DIR / "export.json")

    args = parser.parse_args()
    if args.command == "seed":
        print(f"{load_seed(engine, args.dir)} 行を投入しました")
    else:
        print(f"{export_seed(engine, args.output)} 行を {args.output} へ出力しました")


if __name__ == "__main__":
    main()
