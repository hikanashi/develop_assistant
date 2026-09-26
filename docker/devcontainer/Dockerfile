FROM python:3.11-slim

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# git commit / push はホストPC側からのみ行う運用のため、コンテナ内では git をラッパーに差し替える
RUN mv /usr/bin/git /usr/bin/git.real
COPY git-guard.sh /usr/local/bin/git
RUN chmod +x /usr/local/bin/git

# sudo は入れない(コンテナ内からの権限昇格・保護解除を防ぐため)
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m -s /bin/bash ${USERNAME}

# USDM 要求仕様書の Markdown ⇔ Excel 変換ツール
RUN pip install --no-cache-dir md2usdm

USER ${USERNAME}
WORKDIR /workspace
