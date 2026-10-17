# develop_assistant
AI assistant for developers

## 開発環境 (Dev Container)

VS Code の「Dev Containers: Reopen in Container」でコンテナ内開発ができます(Docker/Rancher Desktop等の起動が必要)。

- コンテナはホストPCから隔離されています(全capability剥奪、特権モード不使用、sudo未導入)。
- `.git` はコンテナ内に読み取り専用でマウントされており、`git commit` / `git push` はコンテナ内から実行できません。コミット・プッシュはホストPC側の git クライアントから行ってください。
