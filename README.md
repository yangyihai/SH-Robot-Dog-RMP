# 上海-研测-狗资源管理平台 (SH Robot Dog RMP)

> 一个面向机器人 / 机器狗设备的内部资源管理平台，支持设备领用、归还、预约排队、报修 / 修复、设备增删改，以及使用记录导出。后端基于 Flask，数据持久化到本地 SQLite，并可选接入飞书群机器人进行动态通知。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)
[![Built with Flask](https://img.shields.io/badge/Built%20with-Flask-000000.svg)](https://flask.palletsprojects.com/)

**RMP** = Resource Management Platform（资源管理平台）。

---

## 目录

- [功能特性](#功能特性)
- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
  - [基础配置](#基础配置)
  - [飞书通知配置（可选）](#飞书通知配置可选)
- [部署](#部署)
  - [本地运行](#本地运行)
  - [systemd 服务部署](#systemd-服务部署)
- [API 参考](#api-参考)
- [数据模型](#数据模型)
- [项目截图](#项目截图)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 功能特性

- 🐕 **设备台账**：维护设备名称、产品线、序列号（SN）及状态（可用 / 故障维修中）。
- 📦 **领用 / 归还**：记录领用人、部门、用途、预计归还时间；归还时仅本人（姓名 + 部门一致）可操作，防止误还他人设备。
- 🔖 **预约排队**：设备占用时可加入预约队列，归还后自动顺位保留给下一位预约人。
- 🔧 **报修 / 修复**：标记设备为故障维修中，修复后恢复可用。
- 🔔 **飞书群通知**：领用、归还、预约、报修、超时催还等动作自动推送到飞书群（可选，凭据通过环境变量注入）。
- 📊 **使用记录**：保留最近若干天记录，支持一键导出 CSV。
- 🧹 **自动清理**：后台定时清理超期数据，超时未归还设备自动群内催还（每设备仅催一次）。

---

## 技术架构

```
┌─────────────┐     HTTP/REST     ┌──────────────────┐     SQLite      ┌─────────────┐
│  浏览器前端   │ ───────────────► │  Flask 后端服务    │ ─────────────► │  devices.db  │
│ HTML/CSS/JS  │ ◄─────────────── │  server.py        │                │  (设备台账)   │
└─────────────┘     JSON 响应     └──────────────────┘                └─────────────┘
                                                  │
                                                  │ 飞书群消息（可选）
                                                  ▼
                                          ┌──────────────────┐
                                          │  飞书开放平台 API  │
                                          │  feishu_notify.py │
                                          └──────────────────┘
```

- **后端**：Python 3 + Flask，单文件 `server.py` 提供全部 REST API。
- **前端**：原生 HTML / CSS / JavaScript，无需构建步骤，直接由 Flask 静态托管。
- **存储**：SQLite（单文件 `devices.db`），零额外依赖、零外部服务。
- **通知**：飞书自建应用「无需任何权限」的群消息推送，凭据全部走环境变量。

---

## 目录结构

```
.
├── server.py                   # Flask 后端服务 + 全部 REST API
├── feishu_notify.py            # 飞书群消息推送（自建应用，无需通讯录权限）
├── SH_Dog_zskj.html            # 前端页面
├── SH_Dog_zskj.css             # 页面样式
├── SH_Dog_zskj.js              # 前端交互逻辑
├── dog-server.service.example  # systemd 服务单元示例（脱敏）
├── requirements.txt            # Python 依赖
├── .gitignore
├── LICENSE
└── README.md
```

> 注：`*.db`（运行时数据库）、`dog-server.service`（含本地路径与密钥）等文件不纳入版本库，详见 `.gitignore`。

---

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/yangyihai/SH-Robot-Dog-RMP.git
cd SH-Robot-Dog-RMP

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务（默认端口 8080）
python3 server.py

# 自定义端口：
PORT=9000 python3 server.py
```

启动后浏览器访问：`http://<本机内网IP>:8080`

首次启动时，`devices.db` 会自动创建并初始化默认设备清单。

---

## 配置说明

### 基础配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PORT`   | `8080` | 服务监听端口 |
| `FEISHU_ADMINS` | `杨怡海,周文成` | 平台管理员（姓名，逗号分隔），用于编辑 / 删除设备权限校验 |

### 飞书通知配置（可选）

1. 在 [飞书开放平台](https://open.feishu.cn) 创建**自建应用**，获取 `App ID` / `App Secret`。
2. 将应用添加到目标群，获取群 `chat_id`。
3. 通过环境变量启用（参考 `dog-server.service.example`）：

   ```bash
   export FEISHU_APP_ID=你的AppID
   export FEISHU_APP_SECRET=你的AppSecret
   export FEISHU_ENABLED=1
   export FEISHU_GROUP_CHAT_ID=你的群chat_id
   export FEISHU_ADMINS=张三,李四
   ```

所有密钥均通过环境变量注入，**请勿硬编码到代码中**。

---

## 部署

### 本地运行

```bash
python3 server.py
```

### systemd 服务部署

参考 `dog-server.service.example`，按实际路径与凭据修改后：

```bash
sudo cp dog-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dog-server
```

---

## API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/state` | 获取全量状态（设备、预约、记录） |
| POST | `/api/checkout` | 领用设备 |
| POST | `/api/return` | 归还设备 |
| POST | `/api/reserve` | 预约排队 |
| POST | `/api/cancel_reserve` | 取消预约 |
| POST | `/api/claim` | 领取已保留设备 |
| POST | `/api/decline_claim` | 放弃领取 |
| POST | `/api/add_device` | 新增设备 |
| POST | `/api/edit_device` | 编辑设备（限测试部门） |
| POST | `/api/delete_device` | 删除设备（限测试部门） |
| POST | `/api/report_broken` | 报修 |
| POST | `/api/repair` | 修复 |
| GET  | `/api/export` | 导出使用记录 CSV |
| POST | `/api/notify_group` | 主动群发提醒 |

---

## 数据模型

- **设备（device）**：`name` / `line` / `sn` / `status`（available / broken）/ `user` / `dept` / `purpose` / `eta` / `reserves` / `reserved_for`
- **使用记录（record）**：领用人、部门、用途、设备、时间等，保留最近若干天
- **预约队列（reserve）**：按设备排队，归还后自动顺位

---

## 项目截图

> 前端为单页 Web 应用，运行后访问 `http://<IP>:8080` 即可看到设备看板。

---

## 贡献指南

欢迎 Issue 与 Pull Request！

1. Fork 本仓库
2. 新建分支：`git checkout -b feature/your-feature`
3. 提交改动：`git commit -m "feat: 你的改动说明"`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

提交前请确保：
- 不包含任何密钥、令牌或本地数据库（`*.db` 已被 `.gitignore` 忽略）
- 飞书等第三方凭据一律通过环境变量注入

---

## 许可证

本项目基于 [MIT License](./LICENSE) 开源。

Copyright (c) 2026 智身科技 (ZhiShen Technology)
