# syntax = docker/dockerfile:1.4.1

from python:3.11-slim-bullseye as python-base

# <<<>>>
# Poetry
# <<<>>>

from python-base as poetry

shell ["/usr/bin/env", "bash", "-c"]
workdir /root/

run --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  <<EOF
  set -o pipefail -o errexit
  apt-get update
EOF

run --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  <<EOF
  set -o pipefail -o errexit
  apt-get install --no-install-recommends --yes \
    curl \
    build-essential
EOF

run --mount=type=cache,target=/root/.cache,sharing=locked \
  <<EOF
  set -o pipefail -o errexit

  export POETRY_VERSION=1.3.2
  curl \
    --silent \
    --show-error \
    --location https://install.python-poetry.org | \
    python
EOF
env PATH="/root/.local/bin:$PATH"

run poetry config virtualenvs.create false

# >>> poetry install

run python -m venv venv

copy pyproject.toml poetry.lock ./
run --mount=type=cache,target=/root/.cache,sharing=locked \
  <<EOF
  set -o pipefail -o errexit

  source venv/bin/activate
  poetry install \
    --remove-untracked \
    --no-root \
    --no-dev \
    --no-interaction
EOF

# <<<>>>
# App
# <<<>>>

from python-base as app

shell ["/usr/bin/env", "bash", "-c"]
run apt-get update && apt-get install --no-install-recommends --yes curl

run <<EOF
  set -o pipefail -o errexit

  curl --output objectivefs_7.2_amd64.deb https://objectivefs.com/user/download/an7dzrz65/objectivefs_7.2_amd64.deb
  apt-get install --yes fuse
  apt-get install --fix-broken

  dpkg -i objectivefs_7.2_amd64.deb
EOF


workdir /root/

copy --from=poetry /root/venv venv
copy ./app app

