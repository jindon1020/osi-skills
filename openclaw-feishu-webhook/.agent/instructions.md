# OpenClaw 飞书 Webhook 配置 Skill

## 概述

这个 Skill 帮助你在阿里云轻量服务器上配置 OpenClaw 使用飞书 Webhook 方式进行通信，将 OpenClaw 从企业微信改为飞书 Webhook 模式连接。

## 前置条件

- 阿里云轻量服务器（已安装 OpenClaw）
- 飞书企业账号（管理员权限）
- 飞书开放平台应用凭证（App ID、App Secret、Verification Token）

## AI Agent 操作指南

当用户请求配置 OpenClaw 飞书 Webhook 时，请按以下步骤操作：

### 1. 收集服务器信息

AI 需要从用户获取以下信息：
- 阿里云服务器 IP 地址
- 服务器 root 密码
- 飞书应用凭证（App ID、App Secret、Verification Token）

### 2. SSH 连接服务器

使用 sshpass 连接服务器：
```bash
sshpass -p '服务器密码' ssh -o StrictHostKeyChecking=no root@服务器IP
```

### 3. 检查当前 OpenClaw 配置

在服务器上执行：
```bash
cat ~/.openclaw/openclaw.json
```

### 4. 更新 OpenClaw 配置文件

确保飞书配置包含以下关键字段：
- `connectionMode`: "webhook"
- `webhookPort`: 3000
- `webhookPath`: "/feishu/events"
- `webhookHost`: "127.0.0.1"

### 5. 配置 Nginx 反向代理

OpenClaw 的 Webhook 服务监听在内网 127.0.0.1:3000，需要通过 Nginx 反向代理暴露给外部。

创建 `/etc/nginx/conf.d/feishu.conf`：
```nginx
server {
    listen 18790;
    server_name _;

    location /feishu/events {
        proxy_pass http://127.0.0.1:3000/feishu/events;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启动 Nginx：
```bash
nginx -t
systemctl enable nginx
systemctl start nginx
```

### 6. 重启 OpenClaw 服务

```bash
systemctl --user restart openclaw-gateway
```

### 7. 提供飞书配置 URL

告诉用户在飞书开放平台配置以下 Webhook 地址：
```
http://服务器IP:18790/feishu/events
```

注意端口是 **18790**（Nginx 监听端口）

## 常见问题排查

### 问题：飞书配置显示"返回数据不是合法的 JSON 格式"

- 检查 Webhook 地址是否正确，端口应为 18790
- 确认 Nginx 已启动并监听 18790 端口

### 问题：无法收到消息

- 确认 Nginx 已启动：`systemctl status nginx`
- 确认端口开放：`netstat -tlnp | grep 18790`
- 检查 OpenClaw 日志：`tail -50 /tmp/openclaw.log`

## 配置汇总

| 配置项 | 说明 |
|--------|------|
| Nginx 端口 | 18790 |
| Webhook 路径 | /feishu/events |
| 内部 Webhook 端口 | 3000 |
