#!/bin/bash

# 单个 Skill 安装脚本
# 用法: curl -sL https://raw.githubusercontent.com/jindon1020/osi-skills/main/install-single.sh | bash -s <skill-name>

set -e

SKILL_NAME="${1:-}"
SKILLS_DIR="$HOME/.claude/skills"
REPO_URL="https://github.com/jindon1020/osi-skills.git"
TEMP_DIR="/tmp/osi-skills-single-$$"

if [ -z "$SKILL_NAME" ]; then
    echo "用法: curl -sL https://raw.githubusercontent.com/jindon1020/osi-skills/main/install-single.sh | bash -s <skill-name>"
    echo "例如: curl -sL ... | bash -s docx"
    exit 1
fi

echo "🧠 安装 Skill: $SKILL_NAME"
echo "=========================="

mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

git clone --depth 1 --single-branch "$REPO_URL" .

DEST="$SKILLS_DIR/$SKILL_NAME"
SOURCE="./$SKILL_NAME"

if [ ! -d "$SOURCE" ]; then
    echo "❌ 未找到 skill: $SKILL_NAME"
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ -e "$DEST" ]; then
    echo "⏭️  $SKILL_NAME 已存在，跳过"
else
    cp -r "$SOURCE" "$DEST"
    echo "✅ 已安装 $SKILL_NAME"
fi

rm -rf "$TEMP_DIR"
echo "💡 请重启 Claude Code 以加载新的 skill"
