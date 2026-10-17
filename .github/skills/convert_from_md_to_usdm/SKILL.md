---
name: convert_from_md_to_usdm
description: 'USDM (Universal Specification Describing Manner) 形式の要求仕様書を Markdown ファイル群として管理し、付属の Python ツールで Excel (.xlsx) と相互変換する。プロジェクト雛形生成、シート追加、Markdown→Excel変換、Excel→Markdown逆変換、ラウンドトリップ比較を行う際に使用する。USDM、要求仕様書、md2usdm、usdm.py に関する作業で使用する。'
---

# USDM Markdown ⇔ Excel 変換

USDM (Universal Specification Describing Manner) 形式の要求仕様書を Markdown ファイル群として管理し、このスキルに同梱された Python スクリプトで Excel と相互変換する。

## セットアップ

```bash
pip3 install --break-system-packages openpyxl
```

## コマンド

| 目的 | コマンド |
|---|---|
| プロジェクト雛形生成 | `python3 ./scripts/usdm.py new <project_name> <output_dir>` |
| シート追加 | `python3 ./scripts/usdm.py add <md_dir> <sheet_name>` |
| Markdown → Excel | `python3 ./scripts/md2usdm.py <md_dir> [output.xlsx]` |
| Excel → Markdown | `python3 ./scripts/usdm2md.py <excel_path> [output_dir]` |
| ラウンドトリップ比較 | `python3 ./scripts/compare_excel.py <original.xlsx> <regenerated.xlsx>` |

## 手順

1. `usdm.py new <project_name> <output_dir>` でプロジェクト雛形（index.md、コンポーネントファイル、xlsx、sheet01）を生成する
2. 必要な数だけ `usdm.py add <md_dir> "{番号}.{カテゴリ名}"` でシートを追加する（シート名は `{番号}.{カテゴリ名}` 形式）
3. 生成された Markdown ファイル群を編集する。書式ルール（ディレクトリ構造、ヘッダーテーブル、上位/下位要件ファイル書式、リッチテキスト記法）は [references/MANUAL.md](./references/MANUAL.md) を参照すること
4. `md2usdm.py <md_dir>` で Excel を生成・再生成する
5. 既存の USDM Excel を Markdown へ逆変換したい場合は `usdm2md.py <excel_path> [output_dir]` を使う
6. 変換の正当性を検証したい場合は `compare_excel.py <original.xlsx> <regenerated.xlsx>` でセル単位比較する

## 注意点

- スクリプトはこのスキルディレクトリ内の `scripts/` にあるため、相対パスまたは絶対パスを指定して実行すること
- `md2usdm.py` は 19列形式で Excel を生成する（Excel テンプレートは不要）
- 要求内容の分析・階層設計・文章作成はこのスキルの範囲外。呼び出し元が要求分析結果を Markdown に落とし込んだ上でこのスキルを使うこと
