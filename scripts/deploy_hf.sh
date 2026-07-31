#!/usr/bin/env bash
# Deploy CityChange to a Hugging Face Space (Docker runtime).
#
# Usage:
#   HF_TOKEN=hf_xxx HF_SPACE=username/citychange scripts/deploy_hf.sh
#   scripts/deploy_hf.sh --stage-only     # build staging dir, don't push
#
# Requirements:
#   - HF_SPACE: the Space id (create it once at huggingface.co/new-space,
#     SDK = Docker, hardware = CPU basic (free)); or let this script create
#     it implicitly by pushing to a Space you own.
#   - HF_TOKEN: a WRITE-scope token from huggingface.co/settings/tokens.
#     The token is used only as a git credential for the push; it is never
#     echoed and never written into the staged repo.
#   - data/outputs/ populated locally (run `citychange benchmark` first) —
#     these bundles are baked into the Space image as always-on demo data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d /tmp/citychange_space_XXXXXX)"
STAGE_ONLY=0
[ "${1:-}" = "--stage-only" ] && STAGE_ONLY=1

echo "staging Space repo in $STAGE"
mkdir -p "$STAGE/prebaked_outputs"
cp -r "$REPO_ROOT/citychange" "$REPO_ROOT/frontend" "$REPO_ROOT/configs" \
      "$REPO_ROOT/pyproject.toml" "$STAGE/"
cp "$REPO_ROOT/deploy/hf/Dockerfile" "$STAGE/Dockerfile"
cp "$REPO_ROOT/deploy/hf/README_SPACE.md" "$STAGE/README.md"
find "$STAGE" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

if [ -d "$REPO_ROOT/data/outputs" ]; then
  cp -r "$REPO_ROOT/data/outputs/." "$STAGE/prebaked_outputs/"
else
  echo "WARNING: data/outputs missing — Space will start empty." >&2
  touch "$STAGE/prebaked_outputs/.gitkeep"
fi

if [ "$STAGE_ONLY" = 1 ]; then
  echo "staged only (no push): $STAGE"
  exit 0
fi

: "${HF_TOKEN:?set HF_TOKEN to a write-scope Hugging Face token}"
: "${HF_SPACE:?set HF_SPACE to <username>/<space-name>}"

cd "$STAGE"
git init -q -b main
git add -A
git -c user.name="citychange-deploy" -c user.email="deploy@citychange.local" \
    commit -q -m "CityChange deployment $(date -u +%Y-%m-%dT%H:%MZ)"

# Token goes into a temporary credential helper, not the remote URL, so it
# never appears in `git remote -v`, the process list, or this script's output.
git config credential.helper \
    '!f() { echo username=citychange; echo "password=$HF_TOKEN"; }; f'
git remote add space "https://huggingface.co/spaces/$HF_SPACE"
git push -q --force space main
git config --unset credential.helper

echo "pushed to https://huggingface.co/spaces/$HF_SPACE"
echo "build logs:  https://huggingface.co/spaces/$HF_SPACE  (App → Logs)"
echo "app URL:     https://${HF_SPACE/\//-}.hf.space   (dots/underscores become dashes)"
