#!/bin/bash

# 本地 Skills 同步脚本
# 将 ~/.claude/skills 中自己创建的 skills 同步到仓库

SOURCE_DIR="$HOME/.claude/skills"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🔄 OSI Skills 同步工具"
echo "======================"

# 检查源目录
if [ ! -d "$SOURCE_DIR" ]; then
    echo "❌ 未找到 skills 目录: $SOURCE_DIR"
    exit 1
fi

cd "$SCRIPT_DIR"

# 排除列表：系统/第三方 skills
EXCLUDE_LIST="agent-browser browser-use code-reviewer find-skills google-veo remotion-best-practices subagent-driven-development veo-use web-design-guidelines"

# 添加 baoyu- 开头的
for item in "$SOURCE_DIR"/baoyu-*; do
    if [ -e "$item" ]; then
        name=$(basename "$item")
        EXCLUDE_LIST="$EXCLUDE_LIST $name"
    fi
done

echo "📂 扫描本地 skills..."
echo ""

# 收集需要同步的 skills
SKILLS_TO_SYNC=""
SKILLS_EXCLUDED=""

for skill_path in "$SOURCE_DIR"/*; do
    [ -e "$skill_path" ] || continue

    skill_name=$(basename "$skill_path")

    # 排除列表检查
    skip=0
    for excluded in $EXCLUDE_LIST; do
        if [ "$skill_name" = "$excluded" ]; then
            skip=1
            break
        fi
    done

    # 排除符号链接
    if [ -L "$skill_path" ]; then
        SKILLS_EXCLUDED="$SKILLS_EXCLUDED $skill_name(符号链接)"
        continue
    fi

    # 只处理目录
    if [ -d "$skill_path" ]; then
        if [ $skip -eq 1 ]; then
            SKILLS_EXCLUDED="$SKILLS_EXCLUDED $skill_name"
        else
            SKILLS_TO_SYNC="$SKILLS_TO_SYNC $skill_name"
        fi
    fi
done

# 显示将同步的 skills
echo "✅ 将同步的 skills:"
for skill in $SKILLS_TO_SYNC; do
    echo "   - $skill"
done
echo ""

# 显示排除的 skills
if [ -n "$SKILLS_EXCLUDED" ]; then
    echo "⏭️  排除的 skills:"
    for skill in $SKILLS_EXCLUDED; do
        echo "   - $skill"
    done
    echo ""
fi

# 同步每个 skill
SYNCED=0
for skill in $SKILLS_TO_SYNC; do
    SOURCE="$SOURCE_DIR/$skill"
    DEST="$SCRIPT_DIR/$skill"

    # 如果目标不存在或与源不同，则复制
    if [ ! -e "$DEST" ]; then
        cp -r "$SOURCE" "$DEST"
        echo "📦 同步 $skill"
        ((SYNCED++))
    else
        SOURCE_MTIME=$(stat -f %m "$SOURCE")
        DEST_MTIME=$(stat -f %m "$DEST")
        if [ "$SOURCE_MTIME" -gt "$DEST_MTIME" ]; then
            rm -rf "$DEST"
            cp -r "$SOURCE" "$DEST"
            echo "📦 同步 $skill (已更新)"
            ((SYNCED++))
        else
            echo "✓ $skill (已是最新)"
        fi
    fi
done

echo ""
echo "====================="
echo "🎉 同步完成! 共同步 $SYNCED 个 skills"
echo ""
echo "请运行以下命令提交更改:"
echo "  git add ."
echo "  git commit -m 'Update skills'"
echo "  git push"
