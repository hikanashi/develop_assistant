# USDM ツール 運用マニュアル

USDM (Universal Specification Describing Manner) 形式のソフトウェア要求仕様書を Markdown で管理し、Excel と双方向変換するツール群。

## セットアップ

```bash
pip3 install --break-system-packages openpyxl
```

## クイックスタート

### 1. プロジェクト作成

```bash
python3 usdm.py new PROJECT_ID my_project
```

生成物:
```
my_project/
├── index.md                              # トップ index (ヘッダーテーブル + シート一覧)
├── PROJECT_ID.md                         # コンポーネント
├── PROJECT_ID.xlsx                       # 生成済み Excel
└── sheet01/
    ├── index.md                          # シート index
    └── PROJECT_ID_R01/
        ├── PROJECT_ID_R01.md             # 上位要件 (u-file)
        └── PROJECT_ID_R01.DM01.md        # 下位要件 (uu-file) + 仕様テーブル
```

### 2. Markdown 編集

要件・仕様を記述:

```markdown
# 【PROJECT_ID_R01】電源管理

## 要件

電源投入時に初期化処理を行い、状態を確認する

### 理由

安全な起動シーケンスを保証するため

### 説明

記載無し

## 下位要件

- [01 電圧確認](./PROJECT_ID_R01.DM01.md "【PROJECT_ID_R01.DM01】")
```

### 3. Excel 再生成

```bash
python3 md2usdm.py my_project
# → my_project/PROJECT_ID.xlsx が更新される
```

### 4. シート追加

```bash
python3 usdm.py add my_project "2.機能要件"
# → sheet02/ が追加され、xlsx が再生成される
```

## Markdown 記法

### ディレクトリ構造

```
project/
├── index.md              # ヘッダーテーブル + シート一覧
├── {ProjectName}.md      # コンポーネント (全シート共通の親要件)
├── sheet01/
│   ├── index.md          # コンポーネントリンク + 上位要件一覧
│   └── {ProjectName}_R01/
│       ├── {ProjectName}_R01.md         # 上位要件 (u-file)
│       └── {ProjectName}_R01.DM01.md    # 下位要件 (uu-file)
├── sheet02/
│   ├── index.md
│   └── ...
```

### ヘッダーテーブル (index.md)

トップレベルの `index.md` にはヘッダーテーブルが含まれる。列名のマークダウン書式でExcel の列構造を指定する:

| 書式 | 意味 | 例 |
|---|---|---|
| `**B**` | 上位要件 (u) 開始列 | 要求ラベル列 |
| `~~C~~` | 下位要件 (uu) 開始列 | 下位要求ラベル列 |
| `` `B` `` | マーカー列 (u/uu/ss/t) | 19列形式のみ |

テンプレート形式 (5列):
```markdown
| 行 | A | **B** | ~~C~~ | D | E |
|---|---|---|---|---|---|
| 列 | 11.0 | 5.25 | 10.375 | 20.625 | 70.625 |
| 1 | カテゴリ名 | 要求 | 要求ID | 要求仕様 | ← |
```

19列形式:
```markdown
| 行 | A | `B` | **C** | ~~D~~ | E | ... | R | S |
|---|---|---|---|---|---|...|---|---|
| 列 | 4.14 | 4.14 | 19.43 | 9.86 | ... | 16.14 | 9.0 |
| 2 | | | 要件及び仕様 | ... | 仕様番号自動生成計算式（隠し列） | |
| 3 | | | | ... | 根拠説明 | | |
| 4 | | | ↑ | ... | ↑ | |
```

### 上位要件ファイル (u-file)

```markdown
↑ [シート名](../index.md)

# 【{仕様番号}】{タイトル}

## 要件

{要件内容}

### 理由

{理由 (不要なら「記載無し」)}

### 説明

{説明 (不要なら「記載無し」)}

## 下位要件

- [{ID} {タイトル}](./{ファイル名}.md "【{仕様番号}】")
```

### 下位要件ファイル (uu-file)

```markdown
↑ [【{親仕様番号}】{親タイトル}](./{親ファイル}.md "【{親仕様番号}】")

# 【{仕様番号}】{タイトル}

## 要件

{要件内容}

### 理由

{理由}

### 説明

{説明}

## 仕様

| 種別 | 内容 | 仕様番号 |
| --- | --- | --- |
| 仕様 | {仕様内容}  | 【{仕様番号}-01】 |
| 仕様 | {仕様内容}  | 【{仕様番号}-02】 |
```

### リッチテキスト

| Markdown | Excel 表示 |
|---|---|
| `**テキスト**` | 赤フォント |
| `~~テキスト~~` | 取消線 |
| `**~~テキスト~~**` | 赤フォント + 取消線 |

### 記載無しプレースホルダー

理由・説明が不要な場合は `記載無し` と記述する。Excel では空セルになる。

## コマンドリファレンス

### usdm.py new

```bash
python3 usdm.py new <project_name> <output_dir>
```

新規 USDM プロジェクトを作成する。Markdown ファイル群 + Excel を生成。

### usdm.py add

```bash
python3 usdm.py add <md_dir> <sheet_name>
```

既存プロジェクトにシートを追加する。index.md を更新し、xlsx を再生成。

### md2usdm.py (逆変換)

```bash
python3 md2usdm.py <md_dir> [output.xlsx]
```

Markdown ファイル群から Excel を生成する (19列形式)。テンプレート不要。

### usdm2md.py (順変換)

```bash
python3 usdm2md.py <excel_path> [output_dir]
```

既存の USDM Excel ファイルを Markdown に変換する。

### compare_excel.py (比較)

```bash
python3 compare_excel.py <original.xlsx> <regenerated.xlsx>
```

2つの Excel ファイルをセル単位で比較する。ラウンドトリップ検証用。

## Excel 機能

生成される Excel には以下の機能が含まれる:

- **アウトライン**: 上位要件 / 下位要件 / 仕様を階層的に折り畳み可能
- **オートフィルタ**: ヘッダー行にフィルタ設定済み
- **セル書式**: ＭＳ ゴシック 9pt、テキスト折り返し、罫線

## 要件追加の手順

### 上位要件を追加

1. `sheetNN/{ProjectName}_{ID}/` ディレクトリを作成
2. u-file (`{ProjectName}_{ID}.md`) を作成
3. シートの `index.md` の下位要件リストにリンクを追加
4. `md2usdm.py` (または `usdm.py` の xlsx 生成) で再生成

### 下位要件を追加

1. 対応する u-file ディレクトリに uu-file (`{ProjectName}_{ID}.DM{XX}.md`) を作成
2. u-file の `## 下位要件` セクションにリンクを追加
3. xlsx を再生成

### 仕様を追加

uu-file の `## 仕様` テーブルに行を追加:

```markdown
| 仕様 | {内容} | 【{仕様番号}】 |
```
