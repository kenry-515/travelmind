# XP Panel Linux 安装 Skill

## 概述

此 Skill 用于让 AI Agent 自动在 Linux x64 服务器上安装 XP Panel（小皮面板）。

安装器支持：

- Ubuntu
- Debian
- CentOS
- Rocky Linux
- AlmaLinux

支持架构：

- x86_64 / amd64 only

---

# Skill 元数据

```yaml
name: xp_panel_installer
version: 1.0.0
description: Install XP Panel on Linux x64 servers
author: XP
license: MIT
```

---

# 功能能力

AI Agent 可以：

- 检测 Linux 发行版
- 检测系统架构
- 检查 root 权限
- 下载 XP Panel 安装脚本
- 执行无人值守安装
- 返回安装日志
- 返回面板访问地址
- 返回默认账号密码

---

# 环境要求

## 系统要求

- Linux x64
- root privileges
- Internet access
- curl or wget

---

# 安装命令

```bash
if [ -f /usr/bin/curl ];then curl -O https://dl.xp.cn/dl/xp/install.sh;else wget -O install.sh https://dl.xp.cn/dl/xp/install.sh;fi;bash install.sh -y
```

---

# 推荐 AI 工作流程

## Step 1: 检测系统架构

```bash
uname -m
```

期望输出：

```text
x86_64
```

拒绝不支持的架构。

---

## Step 2: 检查 Root 权限

```bash
id -u
```

期望输出：

```text
0
```

如果不是 root，则使用 sudo。

---

## Step 3: 下载安装脚本

```bash
if [ -f /usr/bin/curl ];then curl -O https://dl.xp.cn/dl/xp/install.sh;else wget -O install.sh https://dl.xp.cn/dl/xp/install.sh;fi
```

---

## Step 4: 执行安装脚本

```bash
bash install.sh -y
```

---

## Step 5: 返回安装结果

AI 应返回：

- 安装成功/失败
- 面板访问 URL
- 用户名
- 密码
- 已安装服务

---

# 推荐 Tool 定义

```json
{
    "name": "install_xp_panel",
    "description": "Install XP Panel on Linux x64 server",
    "input_schema": {
        "type": "object",
        "properties": {
            "sudo": {
                "type": "boolean",
                "default": true
            }
        }
    }
}
```

---

# 示例 Agent Prompt

```text
Install XP Panel on the target Linux server.

Requirements:
- Verify system architecture is x86_64
- Ensure root privilege
- Download official installer
- Execute unattended installation
- Return access URL and login information
```

---

# 推荐安全检查

## 验证官方域名

仅允许：

```text
https://dl.xp.cn/
```

---

## 阻止不支持的系统

拒绝：

- ARM
- OpenWRT
- Alpine Linux
- 32-bit systems

---

## 安装超时时间

推荐超时时间：

```text
30 minutes
```

---

# 推荐 MCP 集成方式

此 Skill 可集成到：

- MCP Server
- AI Agent
- Claude Desktop
- Cursor
- OpenAI Agents SDK
- LangChain Tools
- AutoGen
- CrewAI

---

# 示例 MCP Tool 流程

```text
AI User Request
    ↓
install_xp_panel
    ↓
check architecture
    ↓
download install.sh
    ↓
execute installer
    ↓
parse installation result
    ↓
return panel information
```

---

# 示例成功响应

```text
XP Panel installed successfully.

Panel URL:
http://SERVER_IP:PORT

Username:
admin

Password:
xxxxxxxx
```

---

# 注意事项

- XP Panel 安装可能需要数分钟。
- 可能需要开放防火墙端口。
- AI Agent 应避免重复安装。
- AI Agent 应保存安装日志。
