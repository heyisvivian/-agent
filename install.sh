#!/usr/bin/env bash
# 把 xhs-agent 的技能装到 Codex CLI 能找到的地方（macOS / Linux）。
#
# Codex 会从这些位置发现 skills：
#     ~/.codex/skills/      ← Codex 原生路径
#     ~/.agents/skills/     ← 跨 agent 通用路径
#     <仓库根>/.agents/skills/  ← 项目级
#
# 默认用符号链接指向仓库里的 skills/，git pull 后技能自动更新。
#
# 用法：
#     ./install.sh              # 符号链接（推荐）
#     ./install.sh --copy       # 复制
#     ./install.sh --uninstall

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/skills"
MODE="link"

for arg in "$@"; do
  case "$arg" in
    --copy)      MODE="copy" ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help)   sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

[[ -d "$SRC" ]] || { echo "找不到 $SRC —— 请在仓库根目录运行。" >&2; exit 1; }

TARGETS=("$HOME/.codex/skills" "$HOME/.agents/skills")

SKILLS=()
for d in "$SRC"/*/; do
  [[ -f "$d/SKILL.md" ]] && SKILLS+=("$(basename "$d")")
done
(( ${#SKILLS[@]} )) || { echo "$SRC 下没有含 SKILL.md 的技能目录。" >&2; exit 1; }

printf '\n  xhs-agent · 小红书创作技能包\n'
printf '  ─────────────────────────────\n'
printf '  仓库：%s\n' "$REPO"
printf '  技能：%d 个 —— %s\n\n' "${#SKILLS[@]}" "$(IFS=', '; echo "${SKILLS[*]}")"

# ---------------------------------------------------------------- 卸载
if [[ "$MODE" == "uninstall" ]]; then
  n=0
  for t in "${TARGETS[@]}"; do
    for s in "${SKILLS[@]}"; do
      if [[ -e "$t/$s" || -L "$t/$s" ]]; then
        rm -rf "$t/$s"; printf '  ✓ 移除 %s\n' "$t/$s"; n=$((n+1))
      fi
    done
  done
  printf '\n  已移除 %d 项。\n\n' "$n"
  exit 0
fi

# ---------------------------------------------------------------- 安装
for t in "${TARGETS[@]}"; do
  mkdir -p "$t"
  printf '  → %s\n' "$t"
  for s in "${SKILLS[@]}"; do
    rm -rf "$t/$s"
    if [[ "$MODE" == "link" ]]; then
      ln -s "$SRC/$s" "$t/$s"; printf '      ✓ %s  (symlink)\n' "$s"
    else
      cp -R "$SRC/$s" "$t/$s"; printf '      ✓ %s  (复制)\n' "$s"
    fi
  done
done

# ---------------------------------------------------------------- 环境自检
printf '\n  环境自检\n  ─────────\n'

PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
if [[ -n "$PY" ]]; then
  printf '  ✓ Python：%s\n' "$($PY --version 2>&1)"
else
  printf '  ✗ 找不到 Python —— 合规扫描、语气统计、字幕生成都需要它\n'
fi

if command -v codex >/dev/null 2>&1; then
  printf '  ✓ Codex CLI：%s\n' "$(command -v codex)"
else
  printf '  ! 没找到 codex 命令（只在 Claude Code 里用可忽略）\n'
fi

# ---------------------------------------------------------------- 冒烟测试
printf '\n  冒烟测试\n  ─────────\n'
if [[ -n "$PY" ]]; then
  set +e
  "$PY" "$REPO/skills/xhs-guard/scripts/xhs_scan.py" \
    --text '这家店最好吃，私我拿地址' --min-tier L2 >/dev/null 2>&1
  code=$?
  set -e
  if [[ $code -eq 1 ]]; then
    printf '  ✓ 合规扫描器工作正常（正确拦下了测试用的违规文案）\n'
  else
    printf '  ✗ 合规扫描器异常（期望 exit 1，实际 %d）\n' "$code"
  fi
fi

# ---------------------------------------------------------------- 下一步
cat <<'EOF'

  装好了。接下来：

  1. 把你发过的笔记放进 samples/（一篇一个 .md，越多越准）
  2. 开 codex，说「学一下我的语气」→ 会生成 profile/voice.md
  3. 然后就可以说「帮我写篇笔记」「做个封面」「审一下这个文案」

EOF
