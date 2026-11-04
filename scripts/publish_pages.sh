#!/usr/bin/env bash
# Publish site/public to GitHub Pages: https://thenguyentrong.github.io/skill-translator/
# Run again after a site change. Uses its own gh-pages branch, the main branch is not touched.
set -euo pipefail
cd "$(dirname "$0")/.."
repo=thenguyentrong/skill-translator
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r site/public/. "$tmp"/
rm -f "$tmp/vercel.json"
touch "$tmp/.nojekyll"
cd "$tmp"
git init -q -b gh-pages
git config user.name thenguyentrong
git config user.email 59952923+thenguyentrong@users.noreply.github.com
git add -A
git commit -q -m "site"
gh auth setup-git
git push -q --force "https://github.com/$repo.git" gh-pages
gh api -X POST "repos/$repo/pages" -f "source[branch]=gh-pages" -f "source[path]=/" >/dev/null 2>&1 || true
echo "published: https://thenguyentrong.github.io/skill-translator/ (first time takes 1-2 minutes)"
