# 离线小册子拼版 API（Python / FastAPI）

按**帖（signature）**对小册子进行拼版：输入总页数、每帖最多纸张数和装订方向（左/右），
按纸张**从外到内**返回每帖各张纸正反面的左右页码。空白页用 `null` 表示。

另提供**章节分帖**接口 `/api/v1/impose/chapters`：按章节首页页码分帖，章节不可跨帖、
相邻章节可合帖，并自动选择空白最少、帖数最少的分帖边界。

还提供**补印复用**接口 `/api/v1/impose/reprint`：输入旧版与新版的页面 ID 列表及改动页，
分别沿用普通拼版规则拼版，逐张判断新版印张可复用哪张旧印张（允许跨帖），否则标记整张重印，
并返回重印总张数。

## 一条命令启动

需要安装 Docker（含 Compose 插件），在项目根目录执行：

```bash
docker compose up -d --build
```

启动成功后服务监听 `http://localhost:8000`（可用 `HOST_PORT` 改宿主机端口），
健康检查 `GET http://localhost:8000/health` 返回 `{"status":"ok"}` 即就绪。

该命令会自动完成：构建镜像 → 安装全部依赖 → 启动 API（容器内 uvicorn 直接拉起，无数据库等额外初始化步骤）。

停止 / 查看日志：

```bash
docker compose down        # 停止
docker compose logs -f     # 查看日志
```

## 必要配置

默认无需任何配置。唯一可选配置是**宿主机端口**（容器内固定 8000）：

```bash
HOST_PORT=9000 docker compose up -d --build
```

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST_PORT` | `8000` | 宿主机暴露端口，通过环境变量覆盖；容器内端口固定为 `8000` |

服务完全离线运行，不连接任何外部服务。

## API 地址与端口

- 服务地址：`http://localhost:8000`（改了 `HOST_PORT` 则对应替换端口）
- 健康检查：`GET http://localhost:8000/health`
- 交互式文档（Swagger UI）：`http://localhost:8000/docs`
- 拼版接口：`POST http://localhost:8000/api/v1/impose`
- 章节分帖拼版接口：`POST http://localhost:8000/api/v1/impose/chapters`
- 补印复用规划接口：`POST http://localhost:8000/api/v1/impose/reprint`

## 接口说明

### 请求

`POST /api/v1/impose`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `total_pages` | 整数 | ≥ 1 | 总页数（正整数） |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 每帖最多纸张数；每帖最多容纳其 **4 倍**页数 |
| `binding` | 字符串 | `left` / `right` | 装订方向：左装订 / 右装订 |

```bash
curl -X POST http://localhost:8000/api/v1/impose \
  -H "Content-Type: application/json" \
  -d '{"total_pages": 16, "max_sheets_per_signature": 4, "binding": "left"}'
```

### 响应

返回帖号 `signature_index` 与帖内纸张序号 `sheet_index`（从 1 开始，1 为最外张），
以及每张纸正面 `front` / 背面 `back` 的左 `left` / 右 `right` 页码；空白页为 `null`。

```json
{
  "total_pages": 16,
  "max_sheets_per_signature": 4,
  "binding": "left",
  "signature_count": 1,
  "signatures": [
    {
      "signature_index": 1,
      "sheet_count": 4,
      "page_count_padded": 16,
      "sheets": [
        {
          "sheet_index": 1,
          "front": { "left": 16, "right": 1 },
          "back":  { "left": 2,  "right": 15 }
        },
        {
          "sheet_index": 2,
          "front": { "left": 14, "right": 3 },
          "back":  { "left": 4,  "right": 13 }
        }
      ]
    }
  ]
}
```

> 实际响应会列出全部 4 张纸，上例只展示前 2 张。

### 拼版规则

1. 按原页顺序分帖，每帖最多容纳 `4 × max_sheets_per_signature` 页；除末帖外各帖均装满。
2. 仅**末帖**在尾部补空白页至 4 的倍数，空白位置页码为 `null`。
3. 左装订（`left`）最外张：
   - 正面（`front`）：左 = 末页，右 = 首页；
   - 背面（`back`）：左 = 次页，右 = 倒数第二页；
   - 之后逐张向内递推（帖页数为 `n`，纸张从外向内序号为 `k = 0,1,2...`，四个页位在帖内的位置索引从 0 计分别为：正左 `n-1-2k`、正右 `2k`、背左 `2k+1`、背右 `n-2-2k`，取出的即为该位置的全局页码，补齐位置为 `null`）。
4. 右装订（`right`）为镜像装订：将左装订结果的**左右页位整体交换**（正反关系不变）。

### 非法参数（4xx）

参数缺失、类型错误、`total_pages` / `max_sheets_per_signature` 小于 1、`binding` 不是
`left`/`right`、包含未定义字段时，均返回 `422 Unprocessable Entity`：

```json
{
  "detail": [
    { "type": "greater_than_equal", "loc": ["body", "total_pages"], "msg": "Input should be greater than or equal to 1" }
  ]
}
```

## 章节分帖拼版（POST /api/v1/impose/chapters）

在 `/api/v1/impose` 的基础上支持**章节感知**分帖：章节不可跨帖，相邻章节可合帖。
本地访问地址 `http://localhost:8000/api/v1/impose/chapters`（改了 `HOST_PORT` 则对应替换端口）。

### 请求

`POST /api/v1/impose/chapters`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `total_pages` | 整数 | ≥ 1 | 总页数（正整数） |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 每帖最多纸张数；每帖实际页数不超过其 **4 倍** |
| `binding` | 字符串 | `left` / `right` | 装订方向：左装订 / 右装订 |
| `chapter_starts` | 整数数组 | 严格递增、首项为 1、末项 ≤ `total_pages` | 各章节首页页码 |

```bash
curl -X POST http://localhost:8000/api/v1/impose/chapters \
  -H "Content-Type: application/json" \
  -d '{"total_pages": 20, "max_sheets_per_signature": 2, "binding": "left", "chapter_starts": [1, 5, 9, 13]}'
```

### 响应

沿用 `sheets` 页位结构（与 `/api/v1/impose` 相同），并为每帖补充原页起止页码
`page_start` / `page_end` 与尾部空白数 `blank_count`：

```json
{
  "total_pages": 20,
  "max_sheets_per_signature": 2,
  "binding": "left",
  "chapter_starts": [1, 5, 9, 13],
  "signature_count": 3,
  "signatures": [
    {
      "signature_index": 1,
      "sheet_count": 1,
      "page_count_padded": 4,
      "page_start": 1,
      "page_end": 4,
      "blank_count": 0,
      "sheets": [
        {
          "sheet_index": 1,
          "front": { "left": 4, "right": 1 },
          "back":  { "left": 2, "right": 3 }
        }
      ]
    }
  ]
}
```

> 上例仅展示第 1 帖；实际响应含全部 3 帖（原页范围 1–4、5–12、13–20）。

### 分帖规则

1. 章节不可跨帖，相邻章节可合帖；每帖实际页数不超过 `4 × max_sheets_per_signature`，
   单章超过该上限时返回 `422 Unprocessable Entity`。
2. 在满足容量约束的分帖方案中，依次最小化：各帖补至 4 的倍数所需**空白页总数** →
   **帖数**；仍相同则优先**最早的分帖边界**。
3. 每帖各自在**尾部**补空白至 4 的倍数（`null`），再按与 `/api/v1/impose`
   相同的正反面拼版规则排列。

### 非法参数（4xx）

除与 `/api/v1/impose` 相同的校验外，`chapter_starts` 为空、首项不为 1、未严格递增、
超过 `total_pages`，或某一单章页数超过 `4 × max_sheets_per_signature` 时，
均返回 `422 Unprocessable Entity`。

## 补印复用规划（POST /api/v1/impose/reprint）

针对“旧版已印好、新版部分内容改动”的补印场景：分别对旧版与新版沿用普通拼版规则
（分帖、仅末帖补空白、左/右装订左右页位）拼版，再逐张判断新版印张能否直接复用旧印张，
不能复用的整张重印，并汇总重印总张数。本地访问地址
`http://localhost:8000/api/v1/impose/reprint`（改了 `HOST_PORT` 则对应替换端口）。

### 请求

`POST /api/v1/impose/reprint`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `old_page_ids` | 字符串数组 | 非空、每项为非空字符串且互不相同 | 旧版页面 ID，按**阅读顺序**排列 |
| `new_page_ids` | 字符串数组 | 非空、每项为非空字符串且互不相同 | 新版页面 ID，按**阅读顺序**排列 |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 两版共用的每帖最多纸张数 |
| `binding` | 字符串 | `left` / `right` | 两版共用的装订方向 |
| `changed_page_ids` | 字符串数组 | 每项必须属于 `new_page_ids` | 新版内容改动的页面 ID；无改动时传 `[]` |

```bash
curl -X POST http://localhost:8000/api/v1/impose/reprint \
  -H "Content-Type: application/json" \
  -d '{"old_page_ids": ["p1", "p2", "p3", "p4"], "new_page_ids": ["p1", "p2", "p3", "p4"], "max_sheets_per_signature": 1, "binding": "left", "changed_page_ids": []}'
```

### 响应

按新版**帖号** `signature_index` 与**张号** `sheet_index`（均从 1 开始）逐张返回：

- `reused`：是否复用旧印张；`reprint` 与其互为相反（`true` = 整张重印）；
- 复用时给出旧版帖号 `old_signature_index` 与旧版张号 `old_sheet_index`（允许跨帖匹配），
  重印时二者为 `null`；
- `front` / `back` 的 `left` / `right` 为该新版印张四个页位上的页面 ID，空白页为 `null`；
- 顶层 `reprint_sheet_count` 为需重印的印张总张数。

```json
{
  "max_sheets_per_signature": 1,
  "binding": "left",
  "signature_count": 1,
  "reprint_sheet_count": 0,
  "signatures": [
    {
      "signature_index": 1,
      "sheet_count": 1,
      "sheets": [
        {
          "sheet_index": 1,
          "reused": true,
          "reprint": false,
          "old_signature_index": 1,
          "old_sheet_index": 1,
          "front": { "left": "p4", "right": "p1" },
          "back":  { "left": "p2", "right": "p3" }
        }
      ]
    }
  ]
}
```

### 复用与重印规则

1. 旧版、新版各自沿用 `/api/v1/impose` 的分帖、补空白（仅末帖尾部补 `null`）和左右页位规则，
   把四个页位上的页码换成页面 ID（空白位为 `null`）。
2. 一张新版印张**仅当**满足全部条件才复用：
   - 四个页位的页面 ID（含同为空白的 `null`）与某张旧印张**完全相同**；
   - 这四个页位上的页面 ID 均不在 `changed_page_ids` 中（空白位天然视为未改动）；
   - 该旧印张尚未被其它新印张匹配——**每张旧印张最多匹配一次**。
3. 匹配**允许跨帖**：按新版帖号、张号顺序，选取第一张满足条件且未占用的旧印张；
   不满足上述任一条件（如页位变化、页上有改动、无对应旧印张）则**整张重印**。
4. 即使页位 ID 与旧版相同，只要其中任一页在 `changed_page_ids` 中，该印张仍须重印。

### 非法参数（4xx）

`old_page_ids` / `new_page_ids` 为空列表或含空字符串、同一版内页面 ID 重复、
`changed_page_ids` 中存在不属于 `new_page_ids` 的 ID、`max_sheets_per_signature` < 1、
`binding` 非法、缺少字段或含未定义字段时，均返回 `422 Unprocessable Entity`。

## 本地开发（不使用 Docker）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest -q
```

## 项目结构

```
.
├── app/
│   ├── __init__.py
│   ├── imposition.py   # 拼版核心算法（分帖 + 帖内拼版）
│   └── main.py         # FastAPI 路由与参数校验
├── tests/              # 算法与 API 测试（pytest）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```
