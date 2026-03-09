#!/bin/bash

# OSI Skills 一键安装脚本
# 用法: curl -sL https://raw.githubusercontent.com/jindon1020/osi-skills/main/install.sh | bash

set -e

SKILLS_DIR="$HOME/.claude/skills"
REPO_URL="https://github.com/jindon1020/osi-skills.git"
TEMP_DIR="/tmp/osi-skills-install-$$"

echo "🧠 OSI Skills 安装器"
echo "====================="

# 检查 Claude Code 是否已安装
if [ ! -d "$SKILLS_DIR" ]; then
    echo "❌ 未找到 Claude Code skills 目录，请先安装 Claude Code"
    exit 1
fi

# 创建临时目录
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

echo "📦 正在下载 skills 仓库..."

# 克隆或更新仓库
if [ -d ".git" ]; then
    git pull --quiet
else
    git clone --depth 1 "$REPO_URL" .
fi

echo "📂 正在安装 skills..."

# 获取所有 skill 目录
SKILLS=$(find . -maxdepth 1 -type d -not -name "." -not -name ".git" -not -name "scripts" | sed 's|^\./||' | sort)

INSTALLED_COUNT=0
SKIP_COUNT=0

for skill in $SKILLS; do
    DEST="$SKILLS_DIR/$skill"

    # 如果目标已存在，询问是否覆盖或跳过
    if [ -e "$DEST" ]; then
        echo "⏭️  跳过 $skill (已存在)"
        ((SKIP_COUNT++))
        continue
    fi

    # 创建符号链接指向仓库中的 skill
    cp -r "$skill" "$DEST"
    echo "✅ 安装 $skill"
    ((INSTALLED_COUNT++))
done

echo ""
echo "====================="
echo "🎉 安装完成!"
echo "   新安装: $INSTALLED_COUNT"
echo "   跳过: $SKIP_COUNT"

# 清理
cd /
rm -rf "$TEMP_DIR"

echo ""
echo "💡 请重启 Claude Code 以加载新的 skills"
