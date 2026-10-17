import argparse
import sys
from pathlib import Path

from app.seed_builder import DEFAULT_DESIGN_DIR, DEFAULT_SEED_DIR, SeedBuildError, build_seed

SEED_DIR = DEFAULT_SEED_DIR


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="seed/*.json をDBへ投入する")
    seed.add_argument("--dir", type=Path, default=SEED_DIR)

    export = sub.add_parser("export", help="DBの内容をシード形式のJSONへ出力する")
    export.add_argument("-o", "--output", type=Path, default=SEED_DIR / "export.json")

    build = sub.add_parser(
        "build-seed", help="design/database/schemas の設計ファイルから seed を生成する"
    )
    build.add_argument("--design-dir", type=Path, default=DEFAULT_DESIGN_DIR)
    build.add_argument("--seed-dir", type=Path, default=SEED_DIR)
    build.add_argument(
        "--check", action="store_true", help="書き込まず、生成ファイルが設計と一致するか確認する"
    )

    args = parser.parse_args()
    if args.command == "build-seed":
        # DBに接続しないため、接続設定 (環境変数) を読み込まずに実行する
        try:
            changed = build_seed(args.design_dir, args.seed_dir, check=args.check)
        except SeedBuildError as e:
            sys.exit(f"エラー: {e}")
        if args.check:
            if changed:
                names = ", ".join(p.name for p in changed)
                sys.exit(f"設計ファイルと一致しません: {names}。build-seed を実行してください")
            print("生成ファイルは設計ファイルと一致しています")
        else:
            print(f"{len(changed)} ファイルを更新しました" if changed else "変更はありません")
        return

    from app.db import engine
    from app.seed_io import export_seed, load_seed

    if args.command == "seed":
        print(f"{load_seed(engine, args.dir)} 行を投入しました")
    else:
        print(f"{export_seed(engine, args.output)} 行を {args.output} へ出力しました")


if __name__ == "__main__":
    main()
