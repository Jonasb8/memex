#!/usr/bin/env bash
# Run the Memex GitHub Action locally without merging a PR.
# Usage:
#   bash scripts/test_action.sh                              # use built-in fixture
#   bash scripts/test_action.sh <github-pr-url>              # fetch real PR data

set -euo pipefail

# ── API key ───────────────────────────────────────────────────────────────────
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Error: ANTHROPIC_API_KEY is not set."
  exit 1
fi

# ── PR data ───────────────────────────────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
  PR_URL="$1"
  # Parse owner/repo and PR number from the URL
  # Expected format: https://github.com/OWNER/REPO/pull/NUMBER
  REPO="$(echo "$PR_URL" | sed -E 's|https://github.com/([^/]+/[^/]+)/pull/.*|\1|')"
  PR_NUMBER="$(echo "$PR_URL" | sed -E 's|.*/pull/([0-9]+).*|\1|')"

  echo "Fetching PR #$PR_NUMBER from $REPO ..."
  PR_JSON="$(gh pr view "$PR_NUMBER" --repo "$REPO" --json title,body,author,url)"
  PR_TITLE="$(echo "$PR_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['title'])")"
  PR_BODY="$(echo "$PR_JSON"  | python3 -c "import sys,json; print(json.load(sys.stdin)['body'] or '')")"
  PR_AUTHOR="$(echo "$PR_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['author']['login'])")"
else
  # ── Built-in fixture (high-signal example) ──────────────────────────────────
  # Swap for the low-signal example to test discard behaviour:
  # PR_TITLE="bump axios from 1.6.0 to 1.7.2"
  # PR_BODY="Bumps axios from 1.6.0 to 1.7.2"
  PR_TITLE="Switch event queue from SQS to Redis Streams"
  PR_BODY="We've been hitting SQS's 256KB message size limit consistently as event
payloads grew. We considered SNS fanout but the filtering model doesn't give us what we
need for per-tenant routing. Redis Streams gives us larger payloads, consumer groups for
exactly-once processing, and we already run Redis for caching so ops overhead is minimal.
The main risk is that Redis becomes a SPOF for both caching and eventing — we're accepting
that for now and will revisit when we move to a multi-region setup."
  PR_URL="https://github.com/local/test/pull/999"
  PR_NUMBER="999"
  PR_AUTHOR="local-test"
  REPO="local/test"
fi

export PR_TITLE PR_BODY PR_URL PR_NUMBER PR_AUTHOR REPO

# ── Stub gh for nudge comments (avoids posting to a real PR) ─────────────────
# Real PR data was already fetched above; only the comment call needs stubbing.
GH_STUB="$(mktemp -d)/gh"
cat > "$GH_STUB" << 'STUB'
#!/usr/bin/env bash
# Pass through 'gh pr view' so get_review_comments still works.
if [[ "$*" == *"--json reviews"* ]]; then
  exec /usr/bin/env gh "$@"
fi
echo "[gh stub] $*" >&2
echo "[]"
STUB
chmod +x "$GH_STUB"
export PATH="$(dirname "$GH_STUB"):$PATH"

# ── Run ───────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")/.."
echo "Running memex action with PR: \"$PR_TITLE\""
echo "────────────────────────────────────────"
python3 -m memex.action
