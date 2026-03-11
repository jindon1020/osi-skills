---
name: publish-to-skills-sh
description: 将自定义 Skill 发布到 skills.sh 平台的完整指南。包括目录结构要求、推送步骤和注册命令。
license: MIT
---

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

在 `.agent/instructions.md` 中详细描述这个 Skill 的作用。

### 3. 推送到 GitHub

```bash
git add your-skill/.agent/
git commit -m "feat: add .agent for skills.sh compatibility"
git push origin main
```

### 4. 在 skills.sh 注册

```bash
npx skills add 用户名/仓库名/子目录路径 --yes
```

## 验证

发布后访问：
```
https://skills.sh/用户名/仓库名/子目录路径
```
