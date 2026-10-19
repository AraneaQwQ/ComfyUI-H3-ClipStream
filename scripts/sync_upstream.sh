#!/usr/bin/env bash
# ============================================================
# sync_upstream.sh — 跟随 NikoDemon80/ComfyUI-H3-Motion-Context 更新
#
# 用法:
#   bash scripts/sync_upstream.sh            # 只读体检：谁和上游不一致、差在哪
#   bash scripts/sync_upstream.sh --diff     # 上面那份报告 + 完整 unified diff
#   bash scripts/sync_upstream.sh --log      # 只看上游提交记录
#   bash scripts/sync_upstream.sh --apply    # 只覆盖「逐字复制」的文件（见下）
#
# 三类文件，处理方式不同（这才是这个脚本存在的理由）:
#   VERBATIM   逐字复制、没有本地改动 —— --apply 可以直接覆盖。
#   PORTED     算法逐字保留，但节点类已经改写成 ComfyUI V3（io.Schema /
#              io.NodeOutput / node_id 带 ClipStream 后缀）。--apply 永远不
#              覆盖它们：那会把 V3 化丢掉。升级时人工比对，只搬算法段。
#   LOCAL_ONLY 我们自己的东西（包注册、前端联动），上游没有对应文件。
#
# 0.7.1 这次升级不是用 --apply 做的，正是这条规则的体现。
# ============================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

EXPECTED_URL="https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context"
UPSTREAM_BRANCH="main"

# 上次移植对齐的上游提交。移植完成后要把它推进到新基线，否则「上游改了什么」
# 会一直回答成历史总量而不是增量。
BASELINE="518c083"          # upstream Release 0.7.1

MODE="status"
case "${1:-}" in
    --diff)  MODE="diff" ;;
    --log)   MODE="log" ;;
    --apply) MODE="apply" ;;
    "")      ;;
    *) echo "unknown option: $1"; exit 2 ;;
esac

# remote 历史上叫 motion-context，现在叫 upstream。按 URL 认，不按名字认。
REMOTE=""
for name in $(git remote); do
    url="$(git remote get-url "$name")"
    if [[ "${url%.git}" == "$EXPECTED_URL" ]]; then
        REMOTE="$name"
        break
    fi
done
if [[ -z "$REMOTE" ]]; then
    echo "没有指向上游组件仓库的 remote，先加一个："
    echo "  git remote add upstream ${EXPECTED_URL}.git"
    exit 1
fi
echo "upstream remote: $REMOTE -> $EXPECTED_URL"

# fetch 失败不报错退出（离线时继续用本地已有的 ref）
if ! git fetch "$REMOTE" "$UPSTREAM_BRANCH" 2>/dev/null; then
    echo "!  fetch 失败（离线？），改用本地的 $REMOTE/$UPSTREAM_BRANCH"
fi
if ! git rev-parse --verify --quiet "$REMOTE/$UPSTREAM_BRANCH" >/dev/null; then
    echo "本地没有 $REMOTE/$UPSTREAM_BRANCH，先 fetch。"
    exit 1
fi
UP_REF="$REMOTE/$UPSTREAM_BRANCH"
echo "upstream head:   $(git log -1 --format='%h %s' "$UP_REF")"
echo "our baseline:    $(git log -1 --format='%h %s' "$BASELINE" 2>/dev/null || echo "$BASELINE (本地没有这个对象)")"
echo ""

# 上游平铺结构 → 我们的路径
VERBATIM=(
    "layout_contract.py:motion_context/layout_contract.py"
    "csrf_guard.py:motion_context/csrf_guard.py"
)
PORTED=(
    "nodes.py:motion_context/nodes.py"
    "probe_node.py:motion_context/probe_node.py"
    "refine_blend.py:motion_context/refine_blend.py"
    "join_match.py:motion_context/join_match.py"
    "sigma_tools.py:motion_context/sigma_tools.py"
    "web/h3_motion_context.js:web/h3_motion_context.js"
)
LOCAL_ONLY=(
    "motion_context/__init__.py"
)

MAPPED=()
for pair in "${VERBATIM[@]}" "${PORTED[@]}"; do
    MAPPED+=("${pair%%:*}")
done

kind_of() {
    local up="$1"
    for pair in "${VERBATIM[@]}"; do
        if [[ "${pair%%:*}" == "$up" ]]; then echo "VERBATIM"; return; fi
    done
    for pair in "${PORTED[@]}"; do
        if [[ "${pair%%:*}" == "$up" ]]; then echo "PORTED"; return; fi
    done
    echo "UNMAPPED"
}

CHANGES_FOUND=0

show_pair() {
    local up="$1" local_path="$2" kind="$3"
    if ! git cat-file -e "$UP_REF:$up" 2>/dev/null; then
        echo "  ~  $local_path  [$kind] 上游没有这个文件（我们自己的？）"
        return
    fi
    if [[ ! -f "$local_path" ]]; then
        echo "  +  $local_path  [$kind] 本地没有：上游新增文件，需要决定是否移植"
        CHANGES_FOUND=1
        return
    fi
    if git diff --quiet "$UP_REF:$up" ":$local_path" 2>/dev/null; then
        echo "  =  $local_path  [$kind] 与上游一致"
        return
    fi
    CHANGES_FOUND=1
    stats="$(diff <(git show "$UP_REF:$up") "$local_path" 2>/dev/null | awk '/^</{a++} /^>/{b++} END{print a+0" "b+0}')"
    up_only="${stats% *}"
    ours_only="${stats#* }"
    echo "  !  $local_path  [$kind] 与上游不同（上游多 $up_only 行 / 我们多 $ours_only 行）"
    if [[ "$kind" == "PORTED" ]]; then
        echo "     PORTED 不会被 --apply 覆盖。要搬算法：git show $UP_REF:$up，人工比对。"
    elif [[ "$MODE" == "apply" ]]; then
        git show "$UP_REF:$up" > "$local_path"
        echo "     -> 已用上游覆盖"
    fi
    if [[ "$MODE" == "diff" ]]; then
        diff -u <(git show "$UP_REF:$up") "$local_path" | sed 's/^/     /' || true
    fi
}

echo "=============================================="
echo "  Motion-Context 上游同步体检"
echo "=============================================="
echo ""
echo "> 自上次基线以来的上游提交（只涉及我们跟踪的文件）:"
git log --oneline "${BASELINE}..${UP_REF}" -- "${MAPPED[@]}" 2>/dev/null || \
    echo "  （没有基线对象，跳过增量日志）"
echo ""

echo "> 逐文件状态:"
for pair in "${VERBATIM[@]}" "${PORTED[@]}"; do
    show_pair "${pair%%:*}" "${pair#*:}" "$(kind_of "${pair%%:*}")"
done
for path in "${LOCAL_ONLY[@]}"; do
    echo "  #  $path  [LOCAL_ONLY] 我们的文件，上游没有对应内容"
done
echo ""

echo "> 上游未映射的文件（最容易漏，需要人工判断是否移植）:"
git ls-tree -r --name-only "$UP_REF" | while read -r up; do
    case "$up" in
        *.py|*.js) ;;
        *) continue ;;
    esac
    covered=0
    for m in "${MAPPED[@]}"; do
        if [[ "$m" == "$up" ]]; then covered=1; fi
    done
    if [[ $covered -eq 0 ]]; then echo "  +  $up"; fi
done
echo ""

echo "=============================================="
if [[ $CHANGES_FOUND -eq 0 ]]; then
    echo "  =  跟踪的文件都与上游一致。"
else
    echo "  !  有差异。PORTED 文件请人工搬算法，不要 --apply。"
fi
echo "=============================================="