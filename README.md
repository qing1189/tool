# ToolBridge

OpenAI / Anthropic 兼容的 Tool Calling 桥接代理，内置 Web 管理面板。

将不支持原生 tool calling 的上游 LLM API 包装为完整支持 `tools` / `tool_choice` / `parallel_tool_calls` 的 OpenAI 兼容端点，同时支持 Anthropic Messages API 的完整转换。纯 Python 标准库实现，零外部依赖。

---

## 项目架构

```
┌─────────────────────────────────────────────────────────┐
│                      ToolBridge                          │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌────────────────────┐  │
│  │  Client  │──▶│  Server  │──▶│   Router/Proxy     │──┼──▶ 上游 LLM API
│  │ (OpenAI/ │   │ (HTTP)   │   │                    │  │
│  │Anthropic)│   │          │   │ - 模型映射         │  │
│  └──────────┘   │          │   │ - 虚拟 Tool Call   │  │
│                 │          │   │ - 流式转发         │  │
│  ┌──────────┐   │          │   │ - Anthropic 转换   │  │
│  │ Web 面板 │──▶│ /admin   │   └────────────────────┘  │
│  │ (浏览器) │   └──────────┘                            │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

### 目录结构

```
toolbridge/
├── __main__.py        # 入口，加载配置启动服务
├── server.py          # HTTP 服务器，请求路由分发
├── router.py          # 业务逻辑：chat、models、anthropic、passthrough
├── proxy.py           # 上游 HTTP 客户端（连接、转发、流式）
├── config.py          # 配置数据类（环境变量 / 文件 / Web面板）
├── config_file.py     # 配置文件读写（~/.toolbridge/config.json）
├── web_admin.py       # Web 管理面板 API（登录、配置CRUD、模型获取）
├── format_openai.py   # OpenAI 格式处理
├── format_anthropic.py# Anthropic ↔ OpenAI 格式转换
├── virtual_tools.py   # 虚拟 tool calling（prompt注入 + 解析）
├── sse.py             # SSE 流式读写
├── model_map.py       # 模型名解析与映射
├── errors.py          # 异常定义
└── static/
    └── index.html     # Web 管理面板前端
```

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 虚拟 Tool Calling | 将工具定义注入 prompt，解析模型输出为标准 tool_calls |
| 原生 Tool Calling 直通 | 支持原生 FC 的模型直接透传，零开销 |
| Anthropic Messages API | 完整支持 `/v1/messages`，tool_use / tool_result / thinking |
| 模型映射 | 外部模型名 → 上游实际模型名 |
| SSE 流式 | 实时逐行转发，支持 OpenAI 和 Anthropic 两种格式 |
| Web 管理面板 | 浏览器管理所有配置，保存即热加载 |
| 动态模型获取 | 一键从上游 `/v1/models` 拉取可用模型 |
| API Key 认证 | 支持多个 Key，保护 `/v1/*` 接口 |
| 面板密码保护 | Token 认证，24h 有效期 |
| 认证头智能处理 | 只填 Key 自动加 `Bearer ` 前缀 |
| 配置持久化 | 保存到磁盘，重启自动加载 |
| 零依赖 | 纯 Python 标准库，无需 pip install |

---

## 快速部署

### Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/qing1189/tool.git && cd tool

# 2. 复制环境变量
cp .env.example .env

# 3. 编辑 .env（也可以启动后通过 Web 面板配置）
vim .env

# 4. 启动
docker compose up -d --build

# 5. 访问管理面板
# http://your-server:8080/admin
```

### Docker 手动部署

```bash
docker build -t toolbridge .

docker run -d \
  --name toolbridge \
  --network host \
  -e PYTHONUNBUFFERED=1 \
  -e UPSTREAM_BASE_URL=http://127.0.0.1:3000 \
  -e ADMIN_PASSWORD="your-password" \
  toolbridge
```

### 直接运行（无 Docker）

```bash
# 最简启动（所有配置通过 Web 面板管理）
python -m toolbridge

# 带环境变量启动
UPSTREAM_BASE_URL=http://127.0.0.1:3000 \
UPSTREAM_AUTH_HEADER="sk-your-key" \
ADMIN_PASSWORD="admin123" \
PORT=8080 \
python -m toolbridge
```

---

## 网络配置说明

本项目使用 `network_mode: host`，容器直接共享宿主机网络栈。

### 上游地址怎么填

| 上游服务位置 | UPSTREAM_BASE_URL 填写 |
|-------------|----------------------|
| 同机器的另一个 Docker 容器（已映射端口） | `http://127.0.0.1:容器映射端口` |
| 同机器直接运行的进程 | `http://127.0.0.1:端口` |
| 远程服务器 | `http://远程IP:端口` |

> **注意：不要用外网 IP 访问本机服务。** 很多服务器不支持 hairpin NAT（外网 IP 回环到本机），会导致超时。同机器的服务统一用 `127.0.0.1`。

### 端口冲突

`network_mode: host` 下容器直接占用宿主机端口。如果默认 8080 被占用，在 `.env` 里设置：

```bash
PORT=9090
```

---

## Web 管理面板

启动后访问 `http://your-server:8080/admin`。

### 面板功能

- **上游配置**：API 地址、认证头（只填 Key 自动加 Bearer）、超时
- **API Key 管理**：添加/删除/随机生成客户端访问 Key
- **模型管理**：从上游动态获取 + 手动添加公开模型列表
- **模型映射**：可视化管理外部名 → 上游名
- **服务配置**：监听端口、重试策略
- **密码管理**：修改/取消面板密码
- **热加载**：保存即生效，无需重启

### 面板密码

| 配置 | 行为 |
|------|------|
| `ADMIN_PASSWORD` 为空 | 免密访问 |
| `ADMIN_PASSWORD=xxx` | 需要登录（Token 24h 有效） |
| 面板内修改密码 | 立即生效，所有会话失效 |
| 面板内密码设为空 | 取消密码保护 |

---

## API Key 认证

保护 `/v1/*` 接口，防止未授权调用。

### 配置

```bash
# 环境变量（JSON 数组）
API_KEYS_JSON='["sk-key1","sk-key2","sk-key3"]'

# 或通过 Web 面板管理（支持随机生成）
```

### 客户端使用

```bash
curl http://your-server:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-key1" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hello"}]}'
```

### 规则

| 条件 | 行为 |
|------|------|
| 未配置任何 Key | 所有请求放行（开放访问） |
| 配置了 Key，请求携带有效 Key | 放行 |
| 配置了 Key，请求未携带或 Key 无效 | 返回 401 |
| `/health`、`/admin` | 永远不需要 Key |

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8080` | 监听端口 |
| `UPSTREAM_BASE_URL` | `http://127.0.0.1:3000` | 上游 API 地址 |
| `UPSTREAM_AUTH_HEADER` | (空) | 上游认证头（只填 Key 自动加 Bearer） |
| `UPSTREAM_TIMEOUT_SECONDS` | `240` | 上游请求超时秒数 |
| `UPSTREAM_EXTRA_BODY_JSON` | `{}` | 追加到上游请求体的额外字段 |
| `MODEL_MAP_JSON` | `{}` | 模型名映射 JSON |
| `ALLOW_UNMAPPED_MODEL_PASSTHROUGH` | `true` | 未映射模型是否直通上游 |
| `NATIVE_TOOL_MODELS_JSON` | `[]` | 支持原生 tool calling 的模型列表 |
| `PUBLIC_MODEL_IDS_JSON` | `[]` | `/v1/models` 返回的模型 ID |
| `TOOL_PROMPT_PREAMBLE` | (内置) | 虚拟 tool calling 的 prompt 前言 |
| `FC_ERROR_RETRY` | `true` | 解析失败是否自动重试 |
| `FC_ERROR_RETRY_MAX_ATTEMPTS` | `3` | 最大重试次数 |
| `RETRY_DELAY_SECONDS` | `0` | 重试间隔秒数 |
| `ADMIN_PASSWORD` | (空) | 管理面板密码 |
| `API_KEYS_JSON` | `[]` | 客户端 API Key 列表 |

---

## API 端点

### 业务接口（受 API Key 保护）

| 端点 | 说明 |
|------|------|
| `GET /v1/models` | 列出可用模型 |
| `POST /v1/chat/completions` | OpenAI Chat Completions（支持流式） |
| `POST /v1/messages` | Anthropic Messages API（支持流式） |

### 系统接口（无需 Key）

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /admin` | Web 管理面板 |
| `GET /admin/api/status` | 服务状态 |
| `GET /admin/api/auth_check` | 检查面板登录状态 |
| `POST /admin/api/login` | 面板登录 |
| `GET /admin/api/config` | 获取配置（需面板认证） |
| `POST /admin/api/config` | 保存配置并热加载（需面板认证） |
| `POST /admin/api/fetch_models` | 从上游获取模型列表（需面板认证） |
| `POST /admin/api/change_password` | 修改面板密码（需面板认证） |

---

## 工作流程

```
客户端请求 POST /v1/chat/completions
    │
    ├─ API Key 校验（如已配置）
    │
    ├─ 模型名解析（映射 / 直通）
    │
    ├─ 有 tools 参数？
    │   ├─ 是原生 FC 模型 → 直接透传上游
    │   └─ 非原生 → 虚拟 Tool Calling
    │       ├─ 注入工具定义到 system prompt
    │       ├─ 请求上游
    │       ├─ 解析模型输出中的工具调用
    │       └─ 返回标准 tool_calls 格式
    │
    └─ 无 tools → 直接透传上游
```

---

## 许可证

MIT
