# 网络搜索 / 抓取接口说明书

> 聚合多个免费与免费层级（free-tier）搜索/抓取供应商的统一接口。
> 与 LLM 聚合（`model="auto"`）同一思路：**一个请求格式，多家上游，失败自动级联**。

---

## 目录

- [概述](#概述)
- [供应商一览](#供应商一览)
- [快速开始](#快速开始)
- [接口一览](#接口一览)
- [1. 列出供应商与参数](#1-列出供应商与参数)
- [2. 搜索 /v1/network/search](#2-搜索-v1networksearch)
- [3. 抓取 /v1/network/fetch](#3-抓取-v1networkfetch)
- [4. 调度策略详解](#4-调度策略详解)
- [5. 供应商配置](#5-供应商配置)
- [6. 实时余额刷新](#6-实时余额刷新tavily)
- [7. 网络分析](#7-网络分析)
- [错误格式](#错误格式)
- [配置方式](#配置方式)

---

## 概述

把多家**完全免费**和**免费层级限额**的搜索/抓取服务聚合到一个端点后面，目的是把这些额度用满：

| 层级 | 特点 | 供应商 |
|---|---|---|
| `keyless` 免密钥 | 零配置、不限月额度，但限流激进 | Exa、Parallel、Firecrawl、Keenable |
| `quota` 免费层级 | 需 API key、额度可靠，但**每月不用就作废** | Tavily（1000 credits/月）、TinyFish |

两层互补：`quota` 策略优先花掉会过期的月度额度，keyless 四家吸收溢出流量；
命中限流（429）后自动冷却 60 秒并级联到下一家。

### 核心设计

- **统一入口**：调用方只填一个 `provider` 参数，不需要为每家学一套参数名；
  各家差异参数放 `params` 子对象，且会按供应商的参数表校验（写错直接 422，而不是被静默丢弃）。
- **串行级联**：一次请求最多串行尝试多家。刻意不用并发——并发等于一次搜索同时烧掉
  六家的额度，违背聚合的初衷。整链有 20 秒总预算兜底。
- **本地记账**：每次调用的延迟（EWMA）、成功/失败计数、月度用量都落在本地 SQLite，
  供 `latency`/`quota` 策略和网络分析页使用。Tavily 可用 `/usage` 端点同步真实余额。

---

## 供应商一览

| 供应商 | 层级 | 能力 | 密钥 | 默认状态 | 限额 |
|---|---|---|---|---|---|
| `exa` | keyless | search + fetch | 不需要 | 启用 | 未公开（限流后自动冷却） |
| `parallel` | keyless | search + fetch | 不需要 | 启用 | 未公开 |
| `firecrawl` | keyless | search + fetch | 可选（提额） | 启用 | 未公开 |
| `keenable` | keyless | search + fetch | 不需要 | 启用 | 未公开 |
| `tavily` | quota | search + fetch | **必需** | 停用 | 1000 credits/月 |
| `tinyfish` | quota | search + fetch | **必需** | 停用 | 搜索 30/分钟 · 500/小时；抓取 150 URL/分钟 · 1000 URL/天 |

- 免密钥四家开箱即用；`quota` 两家需先配 key（见[供应商配置](#5-供应商配置)）。
- TinyFish 的月度额度未公开，`monthly_quota` 默认为空（按"不限量"参与 `quota` 排序）；
  你可以从 TinyFish 控制台查到实际数字后手动填入。
- Tavily 支持**实时余额刷新**（见[第 6 节](#6-实时余额刷新tavily)）。

---

## 快速开始

```bash
BASE=http://localhost:8000
KEY=sk-orca-...        # 首次启动日志打印，或在仪表盘创建

# 1) 搜索 —— 什么都不配也能跑（走免密钥供应商）
curl -s -X POST $BASE/v1/network/search \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"query":"orcarouter lite","max_results":3}'

# 2) 抓取网页正文
curl -s -X POST $BASE/v1/network/fetch \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"urls":["https://example.com"]}'

# 3) 指定供应商 + 供应商专属参数
curl -s -X POST $BASE/v1/network/search \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"query":"fastapi sse","provider":"tavily",
       "params":{"search_depth":"advanced","topic":"news"}}'
```

响应里的 `provider` 字段是**实际应答的供应商**——`strategy` 挑中的可能不是你猜的那家。

---

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/network/providers` | 列出全部供应商 + 参数元数据 + 实时统计 |
| PUT | `/v1/network/providers/{id}` | 配置密钥 / 启停 / 权重 / 月度额度 |
| DELETE | `/v1/network/providers/{id}` | 清除密钥并恢复默认（行保留，不会删除） |
| POST | `/v1/network/providers/{id}/refresh-quota` | 从供应商拉取实时余额（仅 Tavily） |
| POST | `/v1/network/search` | 网页搜索 |
| POST | `/v1/network/fetch` | 批量抓取网页正文 |
| GET | `/v1/analytics/network/summary` | 汇总 KPI |
| GET | `/v1/analytics/network/recent` | 最近请求明细 |
| GET | `/v1/analytics/network/usage` | 按供应商的用量与延迟 |
| GET | `/v1/analytics/network/quota` | 各家免费额度余量 |

所有接口都需要 `Authorization: Bearer sk-orca-*`（同 LLM 接口；也接受 `x-api-key`）。

---

## 1. 列出供应商与参数

```bash
curl -s "$BASE/v1/network/providers" -H "Authorization: Bearer $KEY"
```

```jsonc
{
  "providers": [{
    "id": "tavily",
    "label": "Tavily",
    "tier": "quota",                 // "keyless" | "quota"
    "requires_key": true,
    "optional_key": false,
    "capabilities": ["fetch", "search"],
    "docs_url": "https://tavily.com",
    "configured": true,              // 能否立即服务流量（keyless 恒为 true）
    "has_key": true,
    "key_source": "db",              // "db" | "env" | null
    "key_prefix": "tvly-abc...6789", // 脱敏前缀
    "is_enabled": true,              // false = 不参与自动选择，也拒绝点名调用
    "weight": 100,                   // random 策略的相对权重，0 = 不自动选中
    "quota": {"monthly": 1000, "used": 150, "remaining": 0.85, "resets_at": "..."},
    "avg_latency_ms": 812,           // 成功调用的 EWMA（失败不计入）
    "success_count": 42,
    "failure_count": 3,
    "cooldown_until": null,          // 非 null = 刚被限流，暂时不参与自动选择
    "last_error": null,
    "supports_usage": true,          // 是否支持实时余额刷新（仅 Tavily）
    "limits": [],                    // 公开限额：[{operation, per, limit}]
    "search": {
      "params": [
        {"name":"search_depth","type":"enum","default":"basic",
         "required":false,"enum":["basic","advanced","fast","ultra-fast"],
         "description":"Latency vs relevance. 'advanced' costs 2 credits..."}
      ],
      "max_results": 20
    },
    "fetch": {"params": [ /* ... */ ], "max_urls": 10}
  }],
  "defaults": {"strategy":"random","strategies":["random","quota","latency","explicit"],
               "timeout_ms":8000,"max_results":5}
}
```

**`params` 元数据的 `type` 只有 4 种**，前端据此动态渲染表单：

| type | 渲染 | 说明 |
|---|---|---|
| `string` | 文本框 | 自由文本 |
| `int` | 数字框 | 可带 `min` / `max` |
| `bool` | 下拉 true/false | |
| `enum` | 下拉框 | 值域在 `enum` 数组 |

筛选参数：`GET /v1/network/providers?capability=search`（或 `fetch`）。

---

## 2. 搜索 /v1/network/search

```jsonc
POST /v1/network/search
{
  "query":       "orcarouter lite",   // 必填，1-512 字符
  "strategy":    "random",            // random | quota | latency | explicit（缺省 random）
  "provider":    "tavily",            // 可选；填了则视为 explicit
  "max_results": 5,                   // 1-50，默认 5
  "params":      {"search_depth": "advanced"},  // 供应商专属参数
  "timeout_ms":  8000                 // 1000-30000，单供应商超时
}
```

响应：

```jsonc
{
  "kind": "search",
  "query": "orcarouter lite",
  "provider": "exa",                  // 实际应答者
  "strategy": "random",
  "requested_provider": null,         // 显式点名时才有值
  "failover_from": ["tavily"],        // 在这家之前尝试失败过的供应商
  "errors": {"tavily": "HTTP 429: ..."},
  "latency_ms": 1204,                 // 整链耗时（含级联）
  "count": 3,
  "results": [
    {"title":"...", "url":"https://...", "snippet":"...", "score": 0.81}
  ]
}
```

`score` 仅 Tavily 返回，其余为 `null`。

**Python 示例**

```python
import httpx

r = httpx.post(
    "http://localhost:8000/v1/network/search",
    headers={"Authorization": "Bearer sk-orca-..."},
    json={"query": "sqlite wal mode", "strategy": "quota", "max_results": 5},
    timeout=30,
)
r.raise_for_status()
for item in r.json()["results"]:
    print(item["title"], "->", item["url"])
```

---

## 3. 抓取 /v1/network/fetch

```jsonc
POST /v1/network/fetch
{
  "urls": ["https://example.com", "https://python.org"],  // 必填，1-10 条
  "strategy": "latency",
  "provider": null,
  "params": {"format": "markdown"},   // 如 TinyFish 的 format/links/page_metadata
  "timeout_ms": 8000
}
```

响应遵循**逐 URL 契约**：返回条目数等于提交数，每条要么有 `content` 要么有非空 `error`，
可以放心按下标/URL 对回结果：

```jsonc
{
  "kind": "fetch",
  "url_count": 2,
  "provider": "keenable",
  "strategy": "latency",
  "requested_provider": null,
  "failover_from": [],
  "errors": {},
  "latency_ms": 749,
  "count": 2,
  "results": [
    {"url":"https://example.com", "title":"Example Domain", "content":"# Example Domain\n...", "error":""},
    {"url":"https://blocked.example", "title":"", "content":"", "error":"target_http_error"}
  ]
}
```

`content` 为 markdown（默认），截断到 200,000 字符。

### SSRF 防护

URL 由调用方提供，但目标是运行在**你内网**的自托管服务，因此提交前会校验：

- 仅允许 `http` / `https`（`file://`、`gopher://` 等一律拒绝）
- 拒绝带 userinfo 的 URL（`https://expected.com@evil.com/` 是伪装手法）
- 拒绝解析到环回 / 私网 / 链路本地 / 云元数据地址的目标
  （`127.0.0.1`、`10.x`、`172.16-31.x`、`192.168.x`、`169.254.169.254`、`::1`，含十进制写法 `http://2130706433`）

被拒时返回 `400` + 原因码（`private_address` / `unsupported_scheme` / `userinfo_not_allowed`），
不回显主机名。

---

## 4. 调度策略详解

四种策略都返回**完整级联链**——链尾不是摆设，头部被限流时就轮到它。

### `random` 随机加权（默认）

按 `weight` 做一次**整链加权洗牌**（是排列，不会重复抽取），把流量随时间摊到各家。
`weight=0` 的供应商不会自动选中，但仍留在级联链尾兜底。

> 选型：不确定就用它。免费额度想"都雨露均沾"是这个策略。

### `quota` 配额均衡

按**剩余月度额度比例**降序：`remaining = (monthly - used) / monthly`。
**未公开额度的（keyless 四家）排在有额度供应商之后**——否则不限量的会把
Tavily 那 1000 credits 挤到月底作废。额度耗尽的那家会 432 后级联。

> 选型：想让免费层级的月度额度在被重置前用掉，用它。

### `latency` 速度优先

按**成功调用的 EWMA 延迟**升序（α=0.2）。没采样过的排最后（不是被剔除——
只有 6 家，严格剔除会让全新安装第一次请求就失败）。失败不计入延迟，
否则一次超时会永久污染排名。

> 选型：延迟敏感的 Agent 工具调用场景。

### `explicit` 指定供应商

传 `provider` 即生效（或显式传 `strategy:"explicit"`）。两点语义：

- **严格校验**：供应商不存在 / 被停用 / 没配 key → 直接 `400`，不静默换人。
- **仍然级联**：点名的那家**调用失败**时会继续走级联链尾，但会在
  `failover_from` 里明说。免费层被限流是常态，"点名"意味着优先，不是排他。

---

## 5. 供应商配置

```bash
# 配置密钥（写入 DB，AES-256-GCM 加密存储；同时自动启用该供应商）
curl -X PUT $BASE/v1/network/providers/tavily \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"api_key":"tvly-abc123456789"}'

# 只调权重（省略的字段不动）
curl -X PUT ... -d '{"weight": 33}'

# 手动设定月度额度（TinyFish 未公开额度时可用）
curl -X PUT ... -d '{"monthly_quota": 500}'

# 停用 / 启用（停用后不参与自动选择，点名调用也会被拒）
curl -X PUT ... -d '{"is_enabled": false}'

# 清除密钥并恢复默认（keyless 恢复启用，quota 恢复停用；行不会消失）
curl -X DELETE $BASE/v1/network/providers/tavily
```

要点：

- **没有"隐藏"开关**。所有注册的供应商始终列出；不想让某家参与自动选择就用
  `is_enabled: false`。早期版本有隐藏功能，但隐藏后连恢复按钮也一起消失，已移除。
- **env 密钥优先级低于 DB**：`TAVILY_API_KEY`（见[配置方式](#配置方式)）可用于零面板配置，
  仪表盘设置的 DB 密钥会覆盖它。env 行在列表里标为 `key_source: "env"`，只能改 env 后重启。

---

## 6. 实时余额刷新（Tavily）

本地 `monthly_used` 只统计**本服务发出**的请求，同一把 key 在别处用了就会漂移。
Tavily 暴露了余额端点，可以拉真实数字回填：

```bash
curl -X POST $BASE/v1/network/providers/tavily/refresh-quota \
  -H "Authorization: Bearer $KEY"
```

```jsonc
{
  "provider": "tavily",
  "quota": {"monthly": 1000, "used": 150, "remaining": 0.85, "resets_at": null},
  "used": 150,
  "remaining": 850,
  "remaining_percent": 85.0,
  "plan": "Bootstrap",                       // 账号当前套餐
  "breakdown": {                             // key 维度的分项用量
    "search_usage": 100, "extract_usage": 25,
    "crawl_usage": 15, "map_usage": 7, "research_usage": 3
  },
  "raw": { /* 供应商原始响应，含 account 块 */ }
}
```

- 取的是 `key.usage / key.limit`（免费档真正生效的额度），并写回 `monthly_quota`/`monthly_used`。
- 不支持余额端点的供应商调用会返回 `409`，明确说明而不是假装成功。
- 仪表盘上 Tavily 行有「配额」按钮触发同样操作。
- TinyFish 无公开余额端点，只能靠本地计数 + 手动 `PUT monthly_quota`。

---

## 7. 网络分析

从 LLM 的 `/v1/analytics/*` 分叉而来，落在独立表 `network_requests_log`
（搜索没有 token/成本，对话没有 url_count，混表会让两边查询永远带着 `kind` 过滤）。

```bash
# 汇总：请求数、成功率、p50/p99、活跃供应商数、按 kind 拆分
curl -s "$BASE/v1/analytics/network/summary?days=7" -H "Authorization: Bearer $KEY"

# 按供应商：请求数、成功率、p50/p99（按请求量降序）
curl -s "$BASE/v1/analytics/network/usage?days=7&kind=search" ...

# 额度：各家已用/月度/剩余百分比/重置时间（不限量显示 null）
curl -s "$BASE/v1/analytics/network/quota" ...

# 明细：kind/provider/provider_requested/strategy/failover_from/延迟/状态
curl -s "$BASE/v1/analytics/network/recent?limit=50&kind=fetch" ...
```

`days` 支持 1-365；`kind` 可选 `search` / `fetch`。隐私约定：`query` 截断到 512 字符，
**fetch 只记 host + URL 数量，从不落正文**。

仪表盘「网络」页（快捷键 `7`）含搜索/抓取调试台与供应商表；「网络分析」页（快捷键 `8`）
是这些接口的可视化。

---

## 错误格式

全局错误信封为 `{"error": {"message": "...", "type": "..."}}`（与 LLM 接口一致）。

| 状态码 | 场景 |
|---|---|
| `400` | 空查询、URL 未过 SSRF 校验、`params` 校验失败、未知/停用供应商、无 key 的点名 |
| `401` | 缺少或无效的 `sk-orca-*` |
| `409` | 启用需密钥的供应商但未配 key；刷新余额但不支持/无 key |
| `422` | 请求体字段越界（如 `urls` 超过 10 条） |
| `502` | 级联链上**所有**供应商都失败，消息带 `(tried: a, b, c)` |

区分两类失败很重要：

- **调用方错误（4xx）**：换供应商也救不了，在级联开始前就拒绝——不会白烧各家额度。
- **上游错误（级联）**：进到适配器的都是供应商侧问题（坏 key、宕机、payload 差异），
  换一家可能就好，所以全部级联；总预算 20s 封顶。

---

## 配置方式

三种方式任选，优先级均为 **DB（仪表盘）> env**：

**HA 附加组件** — `config.yaml` 的 options（Supervisor 配置页）：

```yaml
options:
  tavily_api_key: "tvly-..."
  tinyfish_api_key: "tf-..."
```

`run.sh` 会把 options 逐条转成大写环境变量注入。

**docker-compose / 裸机** — `.env`：

```bash
TAVILY_API_KEY=tvly-...
TINYFISH_API_KEY=tf-...
```

**仪表盘** — 网络页供应商行的「密钥」按钮（加密落库，即时生效）。

免密钥四家无需任何配置。
