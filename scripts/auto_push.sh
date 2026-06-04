#!/usr/bin/env bash
# Claude 세션 종료 시 부동산 프로젝트 변경사항 자동 push
# ~/.claude/settings.json Stop 훅에서 호출됨

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 0

# 변경사항 없으면 종료
git status --porcelain 2>/dev/null | grep -q . || exit 0

git add -A
git commit -m "auto: 세션 동기화 $(date +'%Y-%m-%d %H:%M')"
git push
