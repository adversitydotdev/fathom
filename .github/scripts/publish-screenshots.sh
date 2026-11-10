#!/usr/bin/env bash
# Publishes e2e screenshots to the orphan `ci-screenshots` branch.
#   push to main: replaces main/ (the baseline every PR is diffed against)
#   pull request: diffs against main/, stores changed shots under pr-<n>/<sha>/,
#                 and upserts one PR comment with before/after/diff images.
# A private repo's images render only for people with access, which is the point.
set -euo pipefail

BRANCH=ci-screenshots
SHOTS="$PWD/web/e2e/.screenshots"
MARKER='<!-- verify-screenshots -->'
store="$(mktemp -d)/store"

git config --global user.name "github-actions[bot]"
git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null; then
  git fetch --depth 1 origin "$BRANCH"
  git worktree add --detach "$store" FETCH_HEAD
else
  git worktree add --detach "$store"
  git -C "$store" checkout --orphan "$BRANCH"
  git -C "$store" rm -rfq .
fi

push() {
  git -C "$store" add -A
  if git -C "$store" diff --cached --quiet; then return 0; fi
  git -C "$store" commit -qm "$1"
  for _ in 1 2 3; do
    git -C "$store" push -q origin "HEAD:refs/heads/$BRANCH" && return 0
    git -C "$store" pull -q --rebase origin "$BRANCH"
  done
  return 1
}

if [[ "$GITHUB_EVENT_NAME" == "push" ]]; then
  rm -rf "$store/main" && mkdir -p "$store/main"
  cp "$SHOTS"/sweep-*.png "$store/main/"
  push "main @ ${GITHUB_SHA::7}"
  exit 0
fi

pr="$PR_NUMBER"
sha="${PR_HEAD_SHA::7}"
dest="pr-$pr/$sha"
rm -rf "$store/pr-$pr"
md="$(mktemp)"
node web/e2e/compare.mjs "$store/main" "$SHOTS" \
  --out "$store/$dest" \
  --url "https://github.com/$GITHUB_REPOSITORY/raw/$BRANCH/$dest" \
  --md "$md"
push "pr-$pr @ $sha"

existing="$(gh api "repos/$GITHUB_REPOSITORY/issues/$pr/comments" --paginate \
  --jq ".[] | select(.body | startswith(\"$MARKER\")) | .id" | head -n1)"

# Nothing changed and nothing to update: stay quiet.
if [[ -z "$existing" ]] && grep -q '^\*\*Screenshots:\*\* 0 changed, 0 new, 0 removed' "$md"; then
  exit 0
fi

body="$(mktemp)"
{
  echo "$MARKER"
  echo "### Screenshot diff vs \`main\` at ${sha}"
  echo
  cat "$md"
  echo
  echo "<sub>[Run](${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}) · every page is in the \`screenshots\` artifact</sub>"
} > "$body"

if [[ -n "$existing" ]]; then
  gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$existing" -F "body=@$body" >/dev/null
else
  gh pr comment "$pr" --body-file "$body"
fi
