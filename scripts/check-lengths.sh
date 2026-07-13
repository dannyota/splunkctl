#!/usr/bin/env bash
# check-lengths.sh — enforce the doc/code file-length budget (CLAUDE.md §2).
#
# Python source: 500 lines max. Markdown docs: 450 lines max.
# splunkctl/skill/SKILL.md is exempt (detailed agent reference, completeness
# beats brevity).
#
# docs/commands/*.md are EXEMPT: generated verbatim from the command tree
# (`splunkctl docs generate`), so page size follows the CLI, not authored
# prose.
#
# Exit 1 on any violation.
set -euo pipefail
cd "$(dirname "$0")/.."

MD_MAX=450
PY_MAX=500

violations=0

# --- Markdown docs ---
while IFS= read -r f; do
  [[ "$f" == "splunkctl/skill/SKILL.md" ]] && continue
  [[ "$f" == "PLAN.md" ]] && continue
  n=$(wc -l <"$f")
  if (( n > MD_MAX )); then
    echo "DOC TOO LONG  $f: $n lines (max $MD_MAX) — split or trim"
    violations=$((violations + 1))
  fi
done < <(find . -name '*.md' -not -path './.git/*' -not -path './.claude/*' -not -path './docs/commands/*' | sed 's#^\./##' | sort)

# --- Python source ---
while IFS= read -r f; do
  n=$(wc -l <"$f")
  if (( n > PY_MAX )); then
    echo "PY FILE TOO LONG  $f: $n lines (max $PY_MAX) — split by topic"
    violations=$((violations + 1))
  fi
done < <(find . -name '*.py' -not -path './.git/*' -not -path './.claude/*' | sed 's#^\./##' | sort)

if (( violations > 0 )); then
  echo "FAIL: $violations file(s) over the length budget."
  exit 1
fi
echo "OK: all docs <= $MD_MAX lines, all Python source <= $PY_MAX lines."
