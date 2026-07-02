#!/usr/bin/env bash
# gen-seo.sh — regenerate docs/sitemap.xml, docs/llms.txt, docs/llms-full.txt
# from docs/_sidebar.md + docs/guides/*.md + docs/design/*.md.
#
# Run before committing docs changes. CI validates freshness via --check.
#
# docs/assets/og.png (social link preview) is a static asset, regenerated
# manually only when banner.svg changes:
#   google-chrome --headless=new --disable-gpu --hide-scrollbars \
#     --screenshot=docs/assets/og.png --window-size=1200,300 \
#     file://$PWD/docs/assets/banner.svg
#   pngquant --force --quality=80-95 --output docs/assets/og.png docs/assets/og.png
set -euo pipefail
cd "$(dirname "$0")/.."

SITE="https://splunkctl.danny.vn"
DOCS="docs"
CHECK=false
[[ "${1:-}" == "--check" ]] && CHECK=true

# --- discover pages from _sidebar.md + filesystem ---
declare -a PAGES=()
declare -A TITLES=()
declare -A DESCS=()
declare -A PRIORITIES=()

add_page() {
  local path="$1" title="$2" desc="$3" pri="${4:-0.7}"
  PAGES+=("$path")
  TITLES["$path"]="$title"
  DESCS["$path"]="$desc"
  PRIORITIES["$path"]="$pri"
}

first_para() {
  local f="$1"
  # Grab lines of the first paragraph (non-header, non-quote, non-fence, non-blank),
  # strip markdown formatting, join into one line, truncate to first sentence.
  awk '
    /^```/     { in_fence = !in_fence; next }
    in_fence   { next }
    /^$/       { if (started) exit; next }
    /^[#>|`-]/ { next }
    {
      gsub(/\*\*/, "")
      gsub(/\[([^\]]*)\]\([^)]*\)/, "\\1")
      gsub(/`/, "")
      started = 1
      line = (line ? line " " : "") $0
    }
    END { print line }
  ' "$f" | awk '{
    # Prefer first sentence; fall back to word-boundary truncation at 155 chars.
    if (match($0, /^.{10,155}\. /)) {
      print substr($0, 1, RLENGTH - 1)
    } else if (length($0) > 155) {
      s = substr($0, 1, 155)
      sub(/ [^ ]*$/, "", s)
      print s
    } else {
      print
    }
  }'
}

add_page "/" "Home" "CLI tool to operate Splunk Enterprise as code" "1.0"

# Canonical page order — matches sidebar groups. Pages not listed here but
# present on the filesystem are appended at the end as "Advanced".
ORDERED=(
  guides/install:0.9
  guides/configure:0.8
  guides/doctor:0.8
  guides/search:0.9
  guides/rules:0.9
  guides/alerts:0.8
  guides/dashboards:0.7
  guides/indexes:0.7
  guides/inputs:0.7
  guides/lookups:0.8
  guides/hec:0.7
  guides/parsers:0.7
  guides/apps:0.7
  guides/users:0.7
  guides/knowledge:0.7
  guides/conf:0.7
  guides/state:0.8
  guides/es:0.8
  guides/kvstore:0.7
  guides/audit:0.8
  guides/server:0.7
  guides/datamodels:0.7
  design/architecture:0.6
  design/catalog:0.6
)

declare -A SEEN=()

for entry in "${ORDERED[@]}"; do
  rel="${entry%%:*}"
  pri="${entry##*:}"
  f="$DOCS/${rel}.md"
  [[ -f "$f" ]] || continue
  title="$(head -1 "$f" | sed 's/^# *//')"
  desc="$(first_para "$f")"
  [[ -z "$desc" ]] && desc="$title"
  desc="${desc:0:160}"
  add_page "$rel" "$title" "$desc" "$pri"
  SEEN["$rel"]=1
done

# Pick up any new guide/design pages not in ORDERED.
for f in "$DOCS"/guides/*.md "$DOCS"/design/*.md; do
  [[ -f "$f" ]] || continue
  rel="${f#$DOCS/}"
  rel="${rel%.md}"
  [[ -n "${SEEN[$rel]:-}" ]] && continue
  title="$(head -1 "$f" | sed 's/^# *//')"
  desc="$(first_para "$f")"
  [[ -z "$desc" ]] && desc="$title"
  desc="${desc:0:160}"
  add_page "$rel" "$title" "$desc" "0.7"
done

# --- sitemap.xml ---
sitemap="$DOCS/sitemap.xml"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
  for p in "${PAGES[@]}"; do
    if [[ "$p" == "/" ]]; then
      loc="$SITE/#/"
    else
      loc="$SITE/#/$p"
    fi
    echo "  <url><loc>$loc</loc><priority>${PRIORITIES[$p]}</priority></url>"
  done
  echo '</urlset>'
} > "$sitemap.tmp"

# --- llms.txt ---
llms="$DOCS/llms.txt"
{
  echo "# splunkctl"
  echo ""
  echo "> CLI tool to operate Splunk Enterprise as code — for SOC teams, detection engineers, and AI agents. Python, Click, REST API. Every mutation is dry-run by default; nothing changes until you pass --yes."
  echo ""

  section=""
  for p in "${PAGES[@]}"; do
    [[ "$p" == "/" ]] && continue

    case "$p" in
      guides/install|guides/configure|guides/doctor)
        new_section="Getting started" ;;
      guides/search|guides/rules|guides/alerts|guides/dashboards|guides/indexes|guides/inputs|guides/lookups|guides/hec|guides/parsers|guides/apps|guides/users)
        new_section="Core commands" ;;
      guides/knowledge|guides/conf|guides/state|guides/es|guides/kvstore|guides/audit|guides/server|guides/datamodels)
        new_section="Advanced" ;;
      design/*)
        new_section="Design" ;;
      *)
        new_section="Other" ;;
    esac

    if [[ "$new_section" != "$section" ]]; then
      [[ -n "$section" ]] && echo ""
      section="$new_section"
      echo "## $section"
      echo ""
    fi

    echo "- [${TITLES[$p]}]($SITE/#/$p): ${DESCS[$p]}"
  done

  echo ""
  echo "## Links"
  echo ""
  echo "- [GitHub](https://github.com/dannyota/splunkctl): Source code and releases"
  echo "- [PyPI](https://pypi.org/project/splunkctl/): Python package"
} > "$llms.tmp"

# --- llms-full.txt ---
llmsfull="$DOCS/llms-full.txt"
{
  echo "# splunkctl — full documentation"
  echo ""
  echo "> CLI tool to operate Splunk Enterprise as code — for SOC teams, detection engineers, and AI agents."
  echo ""

  for p in "${PAGES[@]}"; do
    [[ "$p" == "/" ]] && continue
    f="$DOCS/${p}.md"
    [[ -f "$f" ]] || continue
    echo "---"
    echo ""
    echo "## Source: $SITE/#/$p"
    echo ""
    cat "$f"
    echo ""
  done
} > "$llmsfull.tmp"

# --- check mode or write ---
if $CHECK; then
  fail=0
  for pair in "$sitemap:$sitemap.tmp" "$llms:$llms.tmp" "$llmsfull:$llmsfull.tmp"; do
    target="${pair%%:*}"
    tmp="${pair##*:}"
    if [[ ! -f "$target" ]]; then
      echo "MISSING  $target — run: bash scripts/gen-seo.sh"
      fail=1
    elif ! diff -q "$target" "$tmp" >/dev/null 2>&1; then
      echo "STALE    $target — run: bash scripts/gen-seo.sh"
      fail=1
    fi
    rm -f "$tmp"
  done
  if (( fail )); then
    echo "FAIL: SEO assets are out of date."
    exit 1
  fi
  echo "OK: SEO assets are fresh."
  exit 0
fi

mv "$sitemap.tmp" "$sitemap"
mv "$llms.tmp" "$llms"
mv "$llmsfull.tmp" "$llmsfull"
echo "Generated: $sitemap, $llms, $llmsfull"
