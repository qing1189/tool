# ToolBridge

OpenAI / Anthropic 兼容的 tool-calling 桥接代理，内置 Web 管理面板。

将不支持原生 tool calling 的上游 API 包装为支持 `tools` / `tool_choice` / `parallel_tool_calls` 的 OpenAI 兼容端点，同时支持 Anthropic Messages API (`/v1/messages`) 的完整转换。

## 功能

- **虚拟 tool calling**：将工具定义注入 prompt，使用激活标记和 JSON 格式解析模型输出的工具调用
- **原生 tool calling 直通**：对支持原生 tool calling 的模型直接透传，零延迟
- **Anthropic Messages API**：完整支持 `/v1/messages`，包括 `tool_use` / `tool_result` / `thinking` block 转换
- **模型映射**：将外部模型名映射到上游模型名
- **SSE 流式**：支持 OpenAI 和 Anthropic 两种流式格式
- **Web 管理面板**：通过浏览器管理所有配置，修改后即时热加载
- **动态模型获取**：一键从上游拉取可用模型列表
- **面板密码保护**：支持设置管理密码，Token 认证
- **配置持久化**：配置保存到磁盘，重启自动加载
- **零依赖**：纯 Python 标准库，`http.server` + `urllib`

## 快速开始

### Docker Compose（推荐）

```bash
# 1. 复制环境变量文件
cp .env.example .env

# 2. 编辑 .env 设置上游地址和管理密码
#    UPSTREAM_BASE_URL=http://your-upstream:3000
#    ADMIN_PASSWORD=your-secure-password

# 3. 启动
docker compose up -d

# 4. 访问管理面板
#    http://your-server:8080/admin
```

### Docker

```bash
docker build -t toolbridge .

docker run -d \
  --name toolbridge \
  -e UPSTREAM_BASE_URL=http://your-upstream:3000 \
  -e UPSTREAM_AUTH_HEADER="Bearer your-key" \
  -e ADMIN_PASSWORD="your-admin-password" \
  -p 8080:8080 \
  -v toolbridge_config:/root/.toolbridge \
  toolbridge
```

### 直接运行

```bash
# 最简启动（通过 Web 面板配置一切）
ADMIN_PASSWORD=my-password python -m toolbridge

# 完整环境变量启动
UPSTREAM_BASE_URL=http://127.0.0.1:3000 \
UPSTREAM_AUTH_HEADER="Bearer your-key" \
MODEL_MAP_JSON='{"deepseek-chat":"deepseek-v4-flash"}' \
ADMIN_PASSWORD="my-password" \
python -m toolbridge
```

## Web 管理面板

启动后访问 `http://your-server:8080/admin` 即可打开管理面板。

### 面板功能

| 功能 | 说明 |
|------|------|
| 上游配置 | 设置上游 API 地址、认证头、超时等 |
| 认证头智能处理 | 只填 API Key 自动添加 `Bearer ` 前缀 |
| 动态获取模型 | 一键从上游 `/v1/models` 拉取模型列表 |
| 模型管理 | 添加/删除公开模型和原生 tool calling 模型 |
| 模型映射 | 可视化管理外部名→上游名映射 |
| 服务配置 | 监听地址、端口、重试策略等 |
| 热加载 | 保存配置即时生效，无需重启服务 |
| 修改密码 | 在面板内随时修改管理密码 |

### 密码保护

- 设置 `ADMIN_PASSWORD` 环境变量即可启用密码保护
- 不设置则面板免密访问
- 登录后 Token 有效期 24 小时
- 修改密码后所有已登录会话立即失效
- 可在面板内将密码设为空来取消密码保护

### 配置持久化

通过 Web 面板保存的配置会持久化到 `~/.toolbridge/config.json`（Docker 中为 `/root/.toolbridge/config.json`）。

下次启动时优先读取此文件，环境变量作为初始值。通过 Docker volumes 挂载可确保容器重建后配置不丢失。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8080` | 监听端口 |
| `UPSTREAM_BASE_URL` | `http://127.0.0.1:3000` | 上游 API 地址 |
| `UPSTREAM_AUTH_HEADER` | (空) | 上游认证头（只填 key 自动加 Bearer） |
| `UPSTREAM_TIMEOUT_SECONDS` | `240` | 上游请求超时 |
| `UPSTREAM_EXTRA_BODY_JSON` | `{}` | 追加到上游请求的额外字段 |
| `MODEL_MAP_JSON` | `{}` | 模型名映射 |
| `ALLOW_UNMAPPED_MODEL_PASSTHROUGH` | `true` | 未映射模型是否直通 |
| `NATIVE_TOOL_MODELS_JSON` | `[]` | 支持原生 tool calling 的模型列表 |
| `PUBLIC_MODEL_IDS_JSON` | `[]` | `/v1/models` 返回的模型 ID 列表 |
| `TOOL_PROMPT_PREAMBLE` | (内置) | 虚拟 tool calling 的 prompt 前言 |
| `FC_ERROR_RETRY` | `true` | 解析失败时是否自动重试 |
| `FC_ERROR_RETRY_MAX_ATTEMPTS` | `3` | 最大重试次数 |
| `RETRY_DELAY_SECONDS` | `0` | 重试间隔秒数 |
| `ADMIN_PASSWORD` | (空) | 管理面板密码（留空则免密访问） |

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /v1/models` | 列出可用模型 |
| `POST /v1/chat/completions` | OpenAI Chat Completions |
| `POST /v1/messages` | Anthropic Messages API |
| `GET /health` | 健康检查 |
| `GET /admin` | Web 管理面板 |
| `GET /admin/api/status` | 服务状态（无需认证） |
| `GET /admin/api/config` | 获取当前配置 |
| `POST /admin/api/config` | 保存配置并热加载 |
| `POST /admin/api/fetch_models` | 从上游获取模型列表 |
| `POST /admin/api/login` | 管理面板登录 |
| `POST /admin/api/change_password` | 修改管理密码 |

## 许可证

MIT
