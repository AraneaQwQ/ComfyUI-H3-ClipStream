#!/usr/bin/env bash
# ============================================================
# sync_upstream.sh — 跟随 NikoDemon80/ComfyUI-H3-Motion-Context 更新
#
# 用法:
#   bash scripts/sync_upstream.sh          # 查看上游变更（只读，不修改）
#   bash scripts/sync_upstream.sh --apply  # 确认后覆盖 motion_context/ + web/h3_motion_context.js
#
# 原理:
#   1. git fetch upstream
#   2. 对比 upstream/main 和我们本地的 motion_context/ 文件
#   3. --apply 模式: 把上游文件复制过来（保留我们标记为 LOCAL 的文件不动）
# ============================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

UPSTREAM="upstream"
UPSTREAM_BRANCH="main"

# 我们本地修改过、不应被上游覆盖的文件
# 如果以后我们改了 motion_context/ 里的某个文件，把它加到这里
LOCAL_OWNED=(
    # "motion_context/__init__.py"   # ← 示例: 如果我们的 __init__.py 有定制
)

# 上游文件路径 → 我们本地路径 的映射
# 上游是平铺结构，我们放在 motion_context/ 子目录
declare -A FILE_MAP=(
    ["nodes.py"]="motion_context/nodes.py"
    ["layout_contract.py"]="motion_context/layout_contract.py"
    ["csrf_guard.py"]="motion_context/csrf_guard.py"
    ["probe_node.py"]="motion_context/probe_node.py"
    ["web/h3_motion_context.js"]="web/h3_motion_context.js"
)

# 检查是否标记为 LOCAL_OWNED
is_local_owned() {
    local path="$1"
    for f in "${LOCAL_OWNED[@]}"; do
        if [[ "$f" == "$path" ]]; then
            return 0
        fi
    done
    return 1
}

echo "══════════════════════════════════════════════"
echo "  Motion-Context Upstream Sync"
echo "  Upstream: $UPSTREAM/$UPSTREAM_BRANCH"
echo "══════════════════════════════════════════════"
echo ""

# Step 1: Fetch
echo "▶ Fetching upstream..."
git fetch "$UPSTREAM" "$UPSTREAM_BRANCH" 2>&1
echo "  Done."
echo ""

# Step 2: Show what's changed upstream (last 5 commits touching our files)
echo "▶ Recent upstream commits (touching our files):"
git log "$UPSTREAM/$UPSTREAM_BRANCH" --oneline -10 -- \
    nodes.py layout_contract.py csrf_guard.py probe_node.py web/h3_motion_context.js
echo ""

# Step 3: Diff each mapped file
APPLY=false
if [[ "${1:-}" == "--apply" ]]; then
    APPLY=true
fi

CHANGES_FOUND=0

for upstream_path in "${!FILE_MAP[@]}"; do
    local_path="${FILE_MAP[$upstream_path]}"

    # Skip if we own this file
    if is_local_owned "$local_path"; then
        echo "  ⏭️  $local_path  [LOCAL_OWNED — skipped]"
        continue
    fi

    # Compare
    if git diff --quiet "$UPSTREAM/$UPSTREAM_BRANCH:$upstream_path" ":$local_path" 2>/dev/null; then
        echo "  ✅ $local_path  (up to date)"
    else
        CHANGES_FOUND=1
        echo "  📝 $local_path  (DIFFERENT)"

        if $APPLY; then
            # Extract from upstream and overwrite
            git show "$UPSTREAM/$UPSTREAM_BRANCH:$upstream_path" > "$local_path"
            echo "     → overwritten from upstream"
        else
            # Show unified diff (abbreviated)
            echo "     diff (upstream vs ours):"
            diff <(git show "$UPSTREAM/$UPSTREAM_BRANCH:$upstream_path" 2>/dev/null) "$local_path" 2>/dev/null | head -20 || true
            echo "     ... (use --apply to overwrite)"
        fi
    fi
done

echo ""
echo "══════════════════════════════════════════════"

if $APPLY; then
    if [[ $CHANGES_FOUND -eq 1 ]]; then
        echo "  ✅ Sync complete. Review & commit:"
        echo "     git diff"
        echo "     git add -A && git commit -m 'sync: update motion_context from upstream'"
        echo "     git push"
    else
        echo "  ✅ Already up to date. Nothing to do."
    fi
else
    if [[ $CHANGES_FOUND -eq 1 ]]; then
        echo "  ℹ️  Changes detected. Run with --apply to overwrite:"
        echo "     bash scripts/sync_upstream.sh --apply"
    else
        echo "  ✅ Up to date. No changes from upstream."
    fi
fi

echo "══════════════════════════════════════════════"
