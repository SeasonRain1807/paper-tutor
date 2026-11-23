#!/usr/bin/env bash
# paper-tutor installer for macOS / Linux.
# 把 skills/paper-tutor 链接或复制到 DSH / Claude Code / Codex / 通用 Agent Skills 目录。
set -euo pipefail

SKILL_NAME="paper-tutor"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/skills/$SKILL_NAME"

HOSTS="claude,codex"
HOSTS_GIVEN=0
SCOPE="project"
TARGET="$SCRIPT_DIR"
USE_COPY=0
UNINSTALL=0

usage() {
    cat <<'EOF'
用法：./install.sh [选项]

  -H, --hosts LIST      要安装的宿主，逗号分隔：dsh,claude,codex,agents；all 等于全部
                        默认 claude,codex；卸载时默认 all（把装过的都清掉）
  -s, --scope SCOPE     project（默认，装到 --target 指定的项目）或 user（装到 $HOME）
  -t, --target DIR      项目根目录，默认本仓库根目录
  -c, --copy            复制而不是建立链接
  -u, --uninstall       删除本脚本建立过的安装项（只删名为 paper-tutor 的目录）
  -h, --help            显示本帮助

示例：
  ./install.sh --hosts all
  ./install.sh --scope user --hosts claude,codex --copy
  ./install.sh --uninstall
EOF
}

die() { echo "错误：$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        -H|--hosts)     [ $# -ge 2 ] || die "缺少 --hosts 的取值"; HOSTS="$2"; HOSTS_GIVEN=1; shift 2 ;;
        -s|--scope)     [ $# -ge 2 ] || die "缺少 --scope 的取值"; SCOPE="$2"; shift 2 ;;
        -t|--target)    [ $# -ge 2 ] || die "缺少 --target 的取值"; TARGET="$2"; shift 2 ;;
        -c|--copy)      USE_COPY=1; shift ;;
        -u|--uninstall) UNINSTALL=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "未知参数：$1（用 --help 查看用法）" ;;
    esac
done

# 卸载时默认覆盖全部宿主，避免 --hosts all 装完却只清掉 claude/codex
if [ "$UNINSTALL" -eq 1 ] && [ "$HOSTS_GIVEN" -eq 0 ]; then
    HOSTS="all"
fi

case "$SCOPE" in
    project|user) ;;
    *) die "--scope 只能是 project 或 user" ;;
esac

[ -d "$SOURCE" ] || die "找不到 skill 本体：$SOURCE（请在仓库根目录运行本脚本）"

# 宿主 → 项目级相对目录
host_rel() {
    case "$1" in
        dsh)    echo ".dsh/skills" ;;
        claude) echo ".claude/skills" ;;
        codex)  echo ".codex/skills" ;;
        agents) echo ".agents/skills" ;;
        *)      return 1 ;;
    esac
}

host_label() {
    case "$1" in
        dsh)    echo "DeepSeek Harness (DSH)" ;;
        claude) echo "Claude Code" ;;
        codex)  echo "Codex" ;;
        agents) echo "Agent Skills 通用目录" ;;
        *)      echo "$1" ;;
    esac
}

# 展开宿主列表
SELECTED=""
IFS=',' read -r -a RAW <<< "$HOSTS"
for item in "${RAW[@]}"; do
    h="$(echo "$item" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    [ -n "$h" ] || continue
    if [ "$h" = "all" ]; then
        SELECTED="$SELECTED dsh claude codex agents"
        continue
    fi
    case "$h" in
        dsh|claude|codex|agents) SELECTED="$SELECTED $h" ;;
        *) die "未知宿主：$h（可选：dsh, claude, codex, agents, all）" ;;
    esac
done
SELECTED="$(echo "$SELECTED" | tr ' ' '\n' | sort -u | tr '\n' ' ')"
[ -n "${SELECTED// /}" ] || die "没有选中任何宿主"

if [ "$SCOPE" = "user" ]; then
    BASE_ROOT="$HOME"
else
    BASE_ROOT="$(cd -- "$TARGET" && pwd)"
fi

DONE=0
for h in $SELECTED; do
    label="$(host_label "$h")"
    if [ "$SCOPE" = "user" ] && [ "$h" = "dsh" ]; then
        echo "警告：$label 只支持项目级安装（.dsh/skills），已跳过" >&2
        continue
    fi
    rel="$(host_rel "$h")"
    base="$BASE_ROOT/$rel"
    dest="$base/$SKILL_NAME"

    # 目标就是 skill 本体本身（不是链接，而是真的同一份目录）：跳过，绝不删除
    if [ ! -L "$dest" ] && [ -d "$dest" ] && [ "$(cd -- "$dest" 2>/dev/null && pwd -P)" = "$(cd -- "$SOURCE" && pwd -P)" ]; then
        if [ "$UNINSTALL" -eq 1 ]; then
            echo "跳过：$dest 就是 skill 本体本身，未删除"
        else
            echo "已就位（这就是 skill 本体）：$dest"
            DONE=$((DONE + 1))
        fi
        continue
    fi

    if [ "$UNINSTALL" -eq 1 ]; then
        if [ ! -e "$dest" ] && [ ! -L "$dest" ]; then
            echo "未安装：$dest"
            continue
        fi
        if [ -L "$dest" ]; then
            rm -f "$dest"
            echo "已删除链接：$dest"
        elif [ -f "$dest/SKILL.md" ] && [ -d "$dest/scripts" ]; then
            rm -rf "$dest"
            echo "已删除副本：$dest"
        else
            echo "警告：跳过 $dest —— 看起来不是 paper-tutor 的安装目录，未删除任何东西" >&2
        fi
        DONE=$((DONE + 1))
        continue
    fi

    if [ -e "$dest" ] || [ -L "$dest" ]; then
        if [ -L "$dest" ]; then
            # readlink 在部分环境不可用，用物理路径比对判断是否已指向本仓库
            if [ "$(cd -- "$dest" 2>/dev/null && pwd -P)" = "$(cd -- "$SOURCE" && pwd -P)" ]; then
                echo "已是最新链接：$dest"
            else
                echo "已存在链接：$dest（指向别处，未改动）" >&2
            fi
            DONE=$((DONE + 1))
            continue
        fi
        if [ -f "$dest/SKILL.md" ] && [ -d "$dest/scripts" ]; then
            echo "已存在副本：$dest（如需更新，先运行 --uninstall 再装）"
        else
            echo "警告：已存在 $dest，且不像 paper-tutor 的安装项（先手动确认再处理）" >&2
        fi
        continue
    fi

    mkdir -p "$base"
    if [ "$USE_COPY" -eq 1 ]; then
        cp -R "$SOURCE" "$dest"
        echo "已复制到：$dest"
    else
        ln -s "$SOURCE" "$dest" || true
        if [ -L "$dest" ]; then
            echo "已链接到：$dest"
        elif [ -e "$dest" ]; then
            echo "已复制到：$dest（该环境不支持符号链接，已改为副本；Windows 上建议直接用 install.ps1）"
        else
            die "创建 $dest 失败"
        fi
    fi
    DONE=$((DONE + 1))
done

if [ "$UNINSTALL" -eq 0 ] && [ "$DONE" -gt 0 ]; then
    echo
    echo "装好了。触发方式：在会话里把论文交给 Agent，例如「帮我把这篇 paper.pdf 精读一遍」。"
    echo "卸载：再运行一次本脚本并加 --uninstall。"
fi
