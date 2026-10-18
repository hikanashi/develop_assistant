# API Guideline

## 1. 基本方針
- OpenAPI (3.1) を唯一の仕様ソース (SSOT) とする。
- 実装より先に `openapi/openapi.yaml` を更新する。
- API変更を含むPRは、仕様変更を必須とする。

## 2. 命名規則
- Path: kebab-case (`/user-profiles/{userId}`)
- JSON field: camelCase (`createdAt`)
- operationId: `verbResource` (`getUser`, `createOrder`)

## 3. HTTPステータス
- 200: 取得成功
- 201: 作成成功
- 204: 削除成功（レスポンスボディなし）
- 400: 入力項目の指定エラー(必須項目が未指定等)
- 401: 未認証
- 403: 権限なし
- 404: リソースなし
- 409: 競合
- 422: 入力ソースのバリデーションエラー
- 500: サーバー内部エラー

## 4. エラーレスポンス形式
```json
{
  "code": "NOT_FOUND",
  "message": "User not found.",
  "details": null
}
```

`code`: 機械可読な固定コード
`message`: 人間向けメッセージ
`details`: バリデーションエラーの発生個所等の詳細情報。 (要求側がエラー要因を特定するための情報)

## 5. 日付時刻
- ISO8601 (format: date-time) を使用
- タイムゾーンはJSTを推奨

## 6. 認証
- Bearer JWT (Authorization: Bearer <token>)
- 全てのoperationで 認証を必須とする。

## 7. バージョニング
- URLにメジャーバージョンを含める (/v1)
- 破壊的変更時に /v2 を作成する


