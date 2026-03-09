# OSI Skills

我自定义创建的 Claude Code Agent Skills 集合。

## 一键安装所有 Skills

```bash
curl -sL https://raw.githubusercontent.com/jindon1020/osi-skills/main/install.sh | bash
```

## 安装单个 Skill

```bash
# 例如安装 docx skill
curl -sL https://raw.githubusercontent.com/jindon1020/osi-skills/main/install-single.sh | bash -s docx
```

## 包含的 Skills

| Skill 名称 | 描述 |
|-----------|------|
| algorithmic-art | 算法艺术创建工具 |
| brand-guidelines | Anthropic 品牌设计指南 |
| canvas-design | Canvas 设计工具 |
| doc-coauthoring | 文档协作工具 |
| docx | Word 文档处理 |
| feishu-doc-reader | 飞书云文档读取 |
| frontend-design | 前端界面设计 |
| internal-comms | 内部通讯文档 |
| last30days | 最近30天活动追踪 |
| mac-desktop-use | macOS 桌面自动化 |
| mcp-builder | MCP 服务器构建 |
| movie-mv-creator | 音乐视频创作 |
| nano-banana-pro | Google Gemini 图像生成 |
| openclaw-feishu-webhook | OpenClaw 飞书配置 |
| pdf | PDF 处理工具 |
| pptx | PPT 演示文稿 |
| skill-creator | Skill 创建指南 |
| slack-gif-creator | Slack GIF 创作 |
| theme-factory | 主题工厂 |
| ui-ux-pro-max | UI/UX 设计专家 |
| web-artifacts-builder | Web 组件构建器 |
| webapp-testing | Web 应用测试 |
| xlsx | Excel 表格处理 |

## 手动同步本地 Skills

如果你想将自己电脑上创建的 skills 同步到 GitHub：

```bash
# 1. 克隆仓库
git clone https://github.com/jindon1020/osi-skills.git
cd osi-skills

# 2. 运行同步脚本
./sync-skills.sh

# 3. 提交并推送
git add .
git commit -m "Update skills"
git push
```

## 本地 Skills 目录

本地 skills 存放在 `~/.claude/skills/` 目录下。

同步脚本会自动排除以下类型的文件：
- 符号链接（来自其他位置的 skills）
- 隐藏文件
- .zip 等压缩包

## License

MIT
