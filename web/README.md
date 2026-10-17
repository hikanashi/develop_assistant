# web

Next.js (App Router / TypeScript) の Web アプリケーションです。バックエンド ([../backend](../backend/README.md)) の REST API を呼び出します。

`create-next-app` で作成したひな形で、トップページがバックエンドの `/health` を呼び出して接続状態を表示します。

## 起動

Dev Container 内で、バックエンドと Web をそれぞれ起動します。

```bash
cd backend && uvicorn app.main:app --reload --host 0.0.0.0   # :8000
cd web && npm run dev -- -H 0.0.0.0                            # :3000
```

`http://localhost:3000` に「バックエンド: ok」と表示されれば接続できています。依存パッケージは初回のみ `npm install` が必要です。

| コマンド | 内容 |
|---|---|
| `npm run dev` | 開発サーバー |
| `npm run lint` | ESLint |
| `npm run build` / `npm start` | 本番ビルドと起動 |

## バックエンドの呼び出し

| 呼び出し元 | 方法 |
|---|---|
| サーバー側 (Server Components / Route Handlers) | [src/lib/backend.ts](src/lib/backend.ts) の `backendFetch("/health")` |
| ブラウザ | `/api/backend/<パス>` (同一オリジン。[next.config.ts](next.config.ts) の rewrites でバックエンドへ転送) |

バックエンドのURLは環境変数 `BACKEND_URL` で変更できます (既定: `http://localhost:8000`)。

## 注意

- Next.js 16 のため、[AGENTS.md](AGENTS.md) のとおり、実装前に `node_modules/next/dist/docs/` の該当ガイドを確認してください。
- `next.config.ts` で `cacheComponents` を有効にしています。リクエスト時のデータ取得は `<Suspense>` で囲む必要があります (トップページの例を参照)。
