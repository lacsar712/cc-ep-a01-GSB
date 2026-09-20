# 科学实验溯源工作台（Experiment Provenance Workbench）

CQRS + Event Sourcing 全栈示例：命令追加 `event_store`，查询走投影表；Vue 前端查看 Run、事件时间线与血缘。

## How to Run

```bash
cd projects/03-experiment-provenance
docker compose up --build
```

> 镜像默认走 `docker.m.daocloud.io`（便于国内拉取）；前端 npm 使用 `npmmirror`。若你可直连 Docker Hub，可将 Dockerfile / compose 中的镜像前缀改回官方名。

首次启动会：

1. 拉起 PostgreSQL
2. 启动 FastAPI 后端并建表
3. `seed` 写入 2 条已完成 Run + 1 条进行中 Run
4. 构建并启动前端（nginx）

停止：

```bash
docker compose down
```

本地后端测试（可选，需 Python 3.11+）：

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Services / 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3173 |
| Backend API | http://localhost:8173 |
| PostgreSQL | localhost:54373 |

容器内：

- `db`：Postgres `provenance/provenance`，库名 `provenance`
- `backend`：Uvicorn `:8000`
- `seed`：一次性灌数后退出
- `frontend`：nginx `:80`，`/api` 反代到 backend

## 账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| researcher | lab123456 | 可发命令（Start/Metric/Artifact/Complete/Abort） |
| auditor | audit123456 | 只读事件与投影 |

## 数据集指纹反查

按 `dataset_content_sha256` 反查关联 Run（非通用搜索，只认数据集指纹）：

- 入口：顶部导航「指纹反查」（研究员与审计员均可见），打开即有查询区
- 输入 64 位完整指纹 → 精确匹配；输入 7–63 位十六进制前缀 → 前缀匹配
- 结果含 project、name、status、code_commit、启动时间，可点「详情」或「血缘」进入原有页面
- API：`GET /api/dataset-fingerprints/lookup?fingerprint=<hex>`（需登录，两角色均可）

seed 数据的已知数据集指纹（`sha256`）：

| Run | 数据集明文 | dataset_content_sha256 |
|-----|-----------|------------------------|
| protein-folding / AlphaFold baseline v1 | `casp14-subset-v1` | `4b7b1197129c6cb0f3b7be0745b76dc4722385a0aad6095df366fbb7cf3fae79` |
| drug-screen / Kinase panel screen #42 | `kinase-panel-2024q3` | `e2994da08f24ccdecf905c13b51dbc7c4124aa3afa8cb15916c59fbb34e4e98e` |
| protein-folding / MSA augmentation | `casp14-msa-aug-v2` | `8a884be77aa0bfd889ac7827076e8c1e8ae52f39378ab538fe92842973d2ffcb` |

## Verification

1. 打开 http://localhost:3173 ，使用 `researcher` / `lab123456` 登录
2. 在 Run 列表看到 seed 数据（含进行中与已完成）
3. 点击「新建 Run」，填写 project/name、dataset sha、code commit，启动
4. 在详情页记录指标、挂载产物，再 Complete（或 Abort）
5. 打开「事件时间线」确认 version 递增的原始事件
6. 打开「血缘」确认 code_commit、dataset 指纹、artifacts、metrics
7. 健康检查：`GET http://localhost:8173/api/health`
8. 用 `auditor` 登录：可看列表/事件/血缘，命令按钮不可用
9. **指纹反查**：打开「指纹反查」，粘贴上表任一完整指纹（或前 12 位，如 `4b7b1197129c`），列出对应 Run，再点「详情」进入原详情页

终态或 `expected_version` 不匹配时，API 返回 **409**。

## 架构要点

- **命令**：`StartRun` / `RecordMetric` / `AttachArtifact` / `CompleteRun` / `AbortRun`
- **事件**：`RunStarted` / `MetricRecorded` / `ArtifactAttached` / `RunCompleted` / `RunAborted`
- **event_store**：`(aggregate_id, version)` 唯一；冲突 → 409
- **run_projections**：查询侧投影（状态、指标、产物等）
