set shell := ["/usr/bin/env", "bash", "-c"]
set positional-arguments

@default:
  just --list --unsorted

# <<<>>>
# Docker
# <<<>>>

git_hash := `git rev-parse --short=4 HEAD`
git_branch := `inp=$(git rev-parse --abbrev-ref HEAD); echo "${inp//\//--}"`

docker_image_name := "ofs-repro"
docker_registry := "812206152185.dkr.ecr.us-west-2.amazonaws.com"
docker_image_version := docker_image_name + "-" + git_hash + "-" + git_branch
docker_image_full := docker_registry + "/" + docker_image_name + ":" + docker_image_version

# >>> CD
@docker-print-image-version:
  echo {{docker_image_version}}

@docker-print-image-full:
  echo {{docker_image_full}}

# >>> Tools
docker-info:
  #!/usr/bin/env bash
  if [[ -z $(git status --porcelain) ]]; then
    echo "$(tput setaf 4)Commit:$(tput sgr0) $(git rev-parse HEAD)"
  else
    echo "$(tput setaf 1)WIP:$(tput sgr0) Uncommitted changes detected"
  fi
  echo "$(tput setaf 4)Tagged image:$(tput sgr0) {{docker_image_full}}"

@docker-login:
  aws ecr get-login-password --region us-west-2 | \
    docker login --username AWS --password-stdin {{docker_registry}}

@docker-create-repo:
  aws ecr create-repository --repository-name {{docker_image_name}}

@docker-build:
  docker build --platform linux/amd64 --tag {{docker_image_full}} .

@docker-push:
  docker push {{docker_image_full}}

@dbnp: docker-build docker-push

# >>> Run

@start:
  python -m app.main
