#!/usr/bin/env bash
# git commit / push はホストPC側の git クライアントからのみ行う運用のため、
# コンテナ内(Copilot 等)からの実行を明示的にブロックする。
# (.git は docker-compose.yml で読み取り専用マウントしているため、
#  本スクリプトを経由しなくても書き込みはカーネルレベルで失敗する)
set -euo pipefail

REAL_GIT="/usr/bin/git.real"
BLOCKED=(commit push)

skip_next=0
subcmd=""
for arg in "$@"; do
  if [ "$skip_next" = "1" ]; then
    skip_next=0
    continue
  fi
  case "$arg" in
    -C|--git-dir|--work-tree)
      skip_next=1
      continue
      ;;
    -*)
      continue
      ;;
    *)
      subcmd="$arg"
      break
      ;;
  esac
done

for b in "${BLOCKED[@]}"; do
  if [ "$subcmd" = "$b" ]; then
    echo "🚫 このコンテナ内から 'git ${subcmd}' を実行することはできません。" >&2
    echo "   コミット/プッシュはホストPC側の git クライアントから行ってください。" >&2
    exit 1
  fi
done

exec "$REAL_GIT" "$@"
