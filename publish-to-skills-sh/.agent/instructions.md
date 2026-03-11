# 发布 Skill 到 skills.sh 指南

## 概述

这个 Skill 帮助开发者将自定义 Skill 发布到 skills.sh 平台，使其可以被其他 AI Agent 发现和使用。

## 前置条件

- 一个公开的 GitHub 仓库
- Node.js 和 npx 可用
- skills.sh CLI 工具（通过 npx 使用）

## 发布步骤

### 1. 规范化目录结构

skills.sh 通过识别仓库中的 `.agent` 目录来获取指令。需要创建以下结构：

```
your-skill-name/
├── .agent/
│   └── instructions.md  <-- 必填：Skill 的核心 Prompt 逻辑
├── README.md            <-- 可选：说明文档
└── ... 其他文件
```

### 2. 准备 instructions.md

在 `.agent/instructions.md` 中详细描述这个 Skill 的作用。内容应该：
- 告诉 AI Agent 这个 Skill 是什么
- 提供操作指南和步骤
- 包含常见问题排查

### 3. 推送到 GitHub

```bash
git add your-skill/.agent/
git commit -m "feat: add .agent for skills.sh compatibility"
git push origin main
```

### 4. 在 skills.sh 注册

```bash
npx skills add 用户名/仓库名/子目录路径
```

例如：
```bash
npx skills add jindon1020/osi-skills/openclaw-feishu-webhook
```

### 5. 跳过交互式选择（可选）

如果不想手动选择 agents，使用 `--yes` 或 `-y` 参数：

```bash
npx skills add 用户名/仓库名/子目录路径 --yes
```

## 验证

发布后访问以下 URL 检查（通常几分钟内同步）：
```
https://skills.sh/用户名/仓库名/子目录路径
```

## 关键注意事项

1. **仓库权限**：仓库必须是 Public（公开）的
2. **目录结构**：必须包含 `.agent/instructions.md`
3. **路径定位**：npx skills 命令支持子目录
4. **自动收录**：一旦安装，skill 会自动出现在 skills.sh 列表中
