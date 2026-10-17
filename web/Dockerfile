FROM node:22-bookworm-slim

WORKDIR /app

# node_modules 用の名前付きボリュームが node ユーザー所有になるよう、先に作成しておく
RUN mkdir -p /app/node_modules && chown -R node:node /app

USER node
