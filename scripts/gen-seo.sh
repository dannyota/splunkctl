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

check=false
[ "${1:-}" = "--check" ] && check=true

root="$(git rev-parse --show-toplevel)"
docs="$root/docs"
sidebar="$docs/_sidebar.md"
base="https://splunkctl.danny.vn"

[ -f "$sidebar" ] || { echo "error: $sidebar not found" >&2; exit 1; }

if $check; then
  outdir="$(mktemp -d)"
  trap 'rm -rf "$outdir"' EXIT
else
  outdir="$docs"
fi

first_para() {
  awk '
    /^```/ { fence=!fence; next }
    fence { next }
    /^#/ { found=1; next }
    found && /^[^#>|[`-]/ && !/^$/ && !/^---/ {
      gsub(/\*\*/, ""); gsub(/`/, ""); gsub(/\[/, ""); gsub(/\]\([^)]*\)/, "")
      printf "%s ", $0; count++
      if (count >= 3) exit
    }
    found && /^$/ && count > 0 { exit }
  ' "$1" | sed 's/ $//' | awk '{
    if (length <= 150) { print; exit }
    s = substr($0, 1, 150)
    sub(/ [^ ]*$/, "", s)
    print s
  }'
}

# --- sitemap.xml ---

sitemap="$outdir/sitemap.xml"
{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
  echo "  <url><loc>${base}/#/</loc><priority>1.0</priority></url>"

  grep -oP '\(([^)]+\.md)\)|\(([^)]+/)\)' "$sidebar" | tr -d '()' | while read -r href; do
    case "$href" in http*) continue ;; esac
    path="${href%.md}"
    path="${path%/}"
    [ -z "$path" ] && continue
    pri="0.7"
    case "$path" in
      guides/install|guides/search|guides/rules) pri="0.9" ;;
      guides/configure|guides/doctor|guides/alerts|guides/lookups|guides/state|guides/es|guides/audit) pri="0.8" ;;
      design/*) pri="0.6" ;;
    esac
    echo "  <url><loc>${base}/#/${path}</loc><priority>${pri}</priority></url>"
  done

  echo '</urlset>'
} > "$sitemap"

# --- llms.txt ---

llms="$outdir/llms.txt"
{
  echo "# splunkctl"
  echo ""
  echo "> CLI tool to operate Splunk Enterprise and Splunk SOAR as code — for SOC teams, detection engineers, and AI agents. Python, Click, REST API. Every mutation is dry-run by default; nothing changes until you pass --yes."
  echo ""

  while IFS= read -r line; do
    title="$(echo "$line" | sed -n 's/^- \*\*\(.*\)\*\*$/\1/p')"
    if [ -n "$title" ]; then
      echo ""
      echo "## ${title}"
      echo ""
      continue
    fi

    if echo "$line" | grep -qP '^\s*- \['; then
      link_title="$(echo "$line" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')"
      href="$(echo "$line" | sed -n 's/.*(\([^)]*\)).*/\1/p')"
      [ -z "$link_title" ] || [ -z "$href" ] && continue

      case "$href" in
        http*) echo "- [${link_title}](${href})"; continue ;;
      esac

      path="${href%.md}"
      path="${path%/}"
      url="${base}/#/${path}"
      [ -z "$path" ] && url="${base}/#/"

      file="$docs/$href"
      [ "$href" = "/" ] && file="$docs/README.md"
      [ -d "$file" ] && file="${file%/}/README.md"
      desc=""
      if [ -f "$file" ]; then
        desc="$(first_para "$file")"
      fi

      if [ -n "$desc" ]; then
        echo "- [${link_title}](${url}): ${desc}"
      else
        echo "- [${link_title}](${url})"
      fi
    fi
  done < "$sidebar"

  echo ""
  echo "## Links"
  echo ""
  echo "- [GitHub](https://github.com/dannyota/splunkctl): Source code and releases"
  echo "- [PyPI](https://pypi.org/project/splunkctl/): Python package"
} > "$llms"

# --- llms-full.txt ---

llmsfull="$outdir/llms-full.txt"
{
  echo "# splunkctl — full documentation"
  echo ""
  echo "> CLI tool to operate Splunk Enterprise and Splunk SOAR as code — for SOC teams, detection engineers, and AI agents."
  echo ""
  echo "---"

  seen=""
  grep -oP '\(([^)]+)\)' "$sidebar" | tr -d '()' | while read -r href; do
    case "$href" in http*) continue ;; esac
    file="$docs/$href"
    [ "$href" = "/" ] && file="$docs/README.md"
    [[ "$href" == */ ]] && file="${file}README.md"
    [ -d "$file" ] && file="${file}/README.md"
    [ -f "$file" ] || continue
    real="$(realpath "$file")"
    echo "$seen" | grep -qF "$real" && continue
    seen="${seen}${real}"$'\n'
    echo ""
    echo "---"
    echo ""
    cat "$file"
  done
  echo ""
} > "$llmsfull"

# --- check or write ---

if $check; then
  stale=false
  for f in sitemap.xml llms.txt llms-full.txt; do
    if ! diff -q "$outdir/$f" "$docs/$f" >/dev/null 2>&1; then
      echo "stale: $f" >&2
      stale=true
    fi
  done
  if $stale; then
    echo "Run: bash scripts/gen-seo.sh" >&2
    exit 1
  fi
  echo "ok: SEO files up-to-date"
else
  echo "generated: sitemap.xml ($(grep -c '<url>' "$sitemap") URLs), llms.txt ($(wc -l < "$llms") lines), llms-full.txt ($(wc -c < "$llmsfull") bytes)"
fi
