# Docker 部署说明

本文档说明如何把当前前后端工程打包为 Docker 镜像，并在另一台电脑运行。

## 打包范围

镜像只复制当前工程化运行所需内容：

- `backend/app`
- `backend/scripts`
- `backend/legacy`
- `frontend`

不会复制 `old/` 中的旧原型目录、旧工作区数据、向量库、上传文件或本地缓存。

`backend/legacy` 是精简运行时目录，只保留当前新后端仍需懒加载的旧能力文件：

- RAG 相关：`rag.py`、`vector_db.py`、`rerank.py`、`synonyms.py`、`custom_parent_document_retriever.py`
- 翻译相关：`tbox_custom_translator.py`、`translate_*.py`
- SPI 解析：`parse_SPI.py`、`parse_spi/settings`、`parse_spi/template`
- 版本差分脚本：`bin_srcdiff.sh`、`lib_srcdiff.sh`

## 构建并启动

在项目根目录执行：

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
```

项目只保留两个服务镜像文件：

- `backend/Dockerfile`
- `frontend/Dockerfile`

根目录不再保留 Dockerfile，避免误用 `docker build .` 打包出错误镜像。

首次启动后创建登录用户：

```powershell
docker compose exec backend python scripts/create_user.py demo demo123
```

如果你更喜欢模块方式，也可以执行：

```powershell
docker compose exec backend python -m scripts.create_user demo demo123
```

访问地址：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/api/v1/health

## 常用命令

查看日志：

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

停止服务：

```powershell
docker compose down
```

重新构建：

```powershell
docker compose build --no-cache
docker compose up -d
```

## 数据目录

运行数据通过 compose 挂载到宿主机：

```text
./data:/app/data
```

包括：

- SQLite 数据库
- 用户上传文件
- 翻译/SPI/diff 临时工作目录

迁移到另一台电脑时，如果需要保留已有数据，复制 `data/` 目录即可。

## 环境变量

生产或共享环境至少修改：

```text
SEKI_TOKEN_SECRET_KEY
```

如需启用真实 LangGraph Agent：

```text
SEKI_RAG_API_KEY="你的模型 key"
```

如需使用旧 RAG/翻译能力，按需配置：

```text
SEKI_RAG_API_KEY
TRANSLATE_API_KEY
EMBEDDING_API_KEY
RERANK_API_KEY
```

不要把真实 key 提交到仓库。
