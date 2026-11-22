#!/bin/sh
# pre-commit-secret-scan.sh — MemeScope
# Blocks a commit when staged files contain secrets, or when .kiro/ is
# accidentally ignored. Install with:
#   cp .kiro/hooks/pre-commit-secret-scan.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
# Never bypass with `git commit --no-verify`.
set -e

# 1. Refuse if .kiro/ is ignored (Kiroween requires it in the repo).
if git check-ignore -q .kiro/specs/memescope/requirements.md 2>/dev/null; then
  echo "BLOCKED: .kiro/ is ignored by .gitignore — Kiroween requires it in the repo."
  exit 1
fi

# 2. Scan staged files for secret patterns.
PATTERNS='(CMC_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]#][^[:space:]]*)|(api[_-]?key[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9_\-]{16,}["'"'"'])|(sk-[A-Za-z0-9]{20,})|(xox[baprs]-[A-Za-z0-9-]{10,})|(-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)|(ghp_[A-Za-z0-9]{20,})|(github_pat_[A-Za-z0-9_]{20,})'

FOUND=0
for f in $(git diff --cached --name-only --diff-filter=ACM); do
  # Skip the hook itself and binary files.
  case "$f" in
    *.kiro/hooks/*) continue ;;
  esac
  if git show ":$f" 2>/dev/null | grep -E -q "$PATTERNS"; then
    echo "BLOCKED: possible secret in staged file: $f"
    FOUND=1
  fi
done

if [ "$FOUND" -eq 1 ]; then
  echo "Remove the secret (use an env var instead) and stage again."
  exit 1
fi

echo "secret-scan: OK"
exit 0
