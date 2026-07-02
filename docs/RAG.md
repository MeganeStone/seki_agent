# RAG（检索增强生成）详细设计说明

> 本文档描述 Seki Agent 项目中 RAG 子系统的完整实现方案，涵盖文档解析、分割策略、向量索引、检索召回、重排序、生成回答等全链路设计。

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [技术栈](#2-技术栈)
3. [文档解析与加载](#3-文档解析与加载)
4. [文档分割策略](#4-文档分割策略)
5. [向量索引与存储](#5-向量索引与存储)
6. [检索召回策略](#6-检索召回策略)
7. [重排序（Rerank）](#7-重排序rerank)
8. [生成回答（Generation）](#8-生成回答generation)
9. [同义词扩展机制](#9-同义词扩展机制)
10. [增量更新（Diff Update）](#10-增量更新diff-update)
11. [服务集成层](#11-服务集成层)
12. [配置参数汇总](#12-配置参数汇总)
13. [设计亮点](#13-设计亮点)
14. [已知不足与改进方向](#14-已知不足与改进方向)
15. [文件清单](#15-文件清单)

---

## 1. 整体架构概览

本项目采用**两层架构**实现 RAG：

```
┌─────────────────────────────────────────────────────────────┐
│                    新服务层 (backend/app/)                    │
│                                                             │
│  AgentService → AgentRunner → RagAgentTool → RagService     │
│       ↓              ↓             ↓              ↓         │
│  LangGraph      Tool路由      工具适配层      懒加载Legacy    │
└──────────────────────────────────┬──────────────────────────┘
                                   │ 动态导入
┌──────────────────────────────────▼──────────────────────────┐
│                  Legacy RAG 管线 (backend/legacy/)           │
│                                                             │
│  vector_db.py → rag.py → custom_parent_document_retriever   │
│       ↓              ↓              ↓                       │
│  文档解析/索引    检索链构建      自定义父文档检索器           │
│       ↓              ↓              ↓                       │
│  synonyms.py    rerank.py      Chroma + LocalFileStore      │
│  同义词扩展      重排序器        向量库 + 父文档存储          │
└─────────────────────────────────────────────────────────────┘
```

**核心数据流：**

```
用户提问
  → 同义词扩展 (synonyms.py)
  → 融合检索 (向量检索 + BM25)
    → 向量检索: 子块相似度搜索 → 反查父文档 (CustomParentDocumentRetriever)
    → BM25检索: 基于父文档的关键词匹配 (jieba中文分词)
    → 加权融合 (EnsembleRetriever, 权重 0.7:0.3)
  → 重排序 (DashScopeRerank, qwen3-rerank)
  → 上下文组装 (带文件名/页码元数据)
  → LLM 生成回答 (qwen3.7-max)
```

---

## 2. 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| **Embedding 模型** | `DashScopeEmbeddings` (text-embedding-v4) | 阿里云百炼平台，支持中文语义 |
| **向量数据库** | `Chroma` | 本地持久化，集合名 `all_child_docs` |
| **父文档存储** | `LocalFileStore` | 基于 pickle 序列化的本地文件存储 |
| **文档解析** | `unstructured` | 支持 PDF/PPT/Word/Excel 多格式解析 |
| **图片理解** | `MultiModalConversation` (qwen3.5-flash) | 阿里通义千问多模态模型，提取图片中的文字 |
| **中文分词** | `jieba` | BM25 检索器的中文分词器 |
| **重排序模型** | `DashScopeRerank` (qwen3-rerank) | 阿里百炼 Rerank API |
| **生成模型** | `ChatOpenAI` (qwen3.7-max) | 通过 DashScope 兼容 OpenAI 接口 |
| **框架** | `LangChain` + `LangGraph` | 检索链构建 + Agent 编排 |

---

## 3. 文档解析与加载

### 3.1 支持的文件格式

| 格式 | 解析方式 | 聚合策略 |
|------|---------|---------|
| **PDF** | `unstructured.partition` | 按页聚合 |
| **PPTX** | `unstructured.partition` | 按页聚合 |
| **DOCX** | `unstructured.partition` | 按页聚合 |
| **XLSX** | `unstructured.partition` | 按行块聚合（每 10 行 + 表头） |
| **TXT** | `TextLoader` | 直接分割，不做父子拆分 |

### 3.2 解析流程

```
文件输入
  → unstructured.partition(filename, languages=["jpn", "chi_sim", "eng"])
  → 逐元素提取 (Text / Table / Image)
  → 图片元素 → 调用 qwen3.5-flash 多模态模型生成文字描述
  → 同义词增强 (enhance_doc_synonyms)
  → 按文件类型选择聚合策略
  → 输出父文档列表
```

### 3.3 多语言支持

文档解析时指定 `languages=["jpn", "chi_sim", "eng"]`，支持日语、简体中文和英语三种语言的混合文档解析。

### 3.4 图片处理

对于文档中的图片元素，系统会：
1. 通过 `unstructured` 提取图片文件路径
2. 调用阿里通义千问多模态模型 (`qwen3.5-flash`)
3. 使用提示词 `"请仅输出图像中的文本内容"` 提取图片中的文字
4. 将提取的文字作为文档内容替代原始空图片元素

### 3.5 Excel 特殊处理

Excel 文件采用**行块聚合**策略：
- 第一行作为表头，每个数据块都会附带完整表头
- 每个块包含 10 行数据（`chunk_size=10`）
- 元数据记录行范围 (`row_start`, `row_end`)
- 确保每个子块都保留表头上下文，避免语义丢失

---

## 4. 文档分割策略

### 4.1 父子文档（Parent-Child）策略

本项目采用**父子文档分割**策略，核心思想是：
- **父文档**：保留完整的语义上下文（如一整页内容）
- **子文档**：从父文档中切分出的小块，用于精确向量检索
- 检索时先通过子文档匹配，再反查对应的父文档返回给 LLM

```
父文档 (按页聚合的完整内容)
  ├── 子块 1 (300 tokens, overlap 50)
  ├── 子块 2 (300 tokens, overlap 50)
  ├── 子块 3 (300 tokens, overlap 50)
  └── ...
```

### 4.2 分割参数

| 文档类型 | 分割器 | chunk_size | chunk_overlap | 分隔符 |
|---------|--------|-----------|--------------|--------|
| **PDF/PPT/Word** (子块) | `RecursiveCharacterTextSplitter` | 300 | 50 | 默认 |
| **TXT** | `RecursiveCharacterTextSplitter` | 1000 | 200 | `\n\n`, `\n`, `。`, `！`, `？`, `，`, `、`, ` `, `.` |
| **Excel** | 行块聚合 | 10 行/块 | - | - |

### 4.3 Parent ID 关联机制

每个父子文档对通过 `parent_id` 关联：
- `parent_id` 格式：`{文件路径MD5哈希}__{索引号}`
- 使用 MD5 哈希避免文件路径中的特殊字符问题
- 子块和父文档的 metadata 中均包含 `parent_id` 字段

---

## 5. 向量索引与存储

### 5.1 Embedding 模型

- **模型**：`text-embedding-v4`（阿里云百炼 DashScope）
- **提供商**：阿里云百炼平台
- **API**：`DashScopeEmbeddings`

### 5.2 向量数据库

- **引擎**：`Chroma`（langchain_chroma）
- **集合名称**：`all_child_docs`
- **持久化目录**：由环境变量 `VECTOR_DB_DIR` 指定
- **存储内容**：仅存储子块（child chunks）的向量及元数据

### 5.3 父文档存储

- **引擎**：`LocalFileStore`（LangChain 本地文件存储）
- **持久化目录**：由环境变量 `PARENT_STORE_DIR` 指定
- **序列化方式**：`pickle.dumps(Document)` / `pickle.loads(data)`
- **键名**：`parent_id`（如 `a1b2c3d4__0`）

### 5.4 元数据字段

每个文档块包含以下元数据：

| 字段 | 说明 |
|------|------|
| `file_name` | 源文件名 |
| `file_path` | 源文件完整路径 |
| `file_mtime` | 文件修改时间戳（用于增量更新） |
| `parent_id` | 父文档关联 ID |
| `page_number` | 页码（PDF/PPT/Word） |
| `element_type` | 元素类型（Title/Table/Image 等） |
| `aggregated` | 是否为聚合后的文档 |
| `doc_type` | 文档类型标记（仅 TXT） |

---

## 6. 检索召回策略

本项目采用**多路召回 + 融合**的检索策略，是整个 RAG 系统的核心。

### 6.1 检索管线总览

```
用户查询
  │
  ├──→ [路径A] 向量检索 (CustomParentDocumentRetriever)
  │       → Chroma similarity_search(k=20) 子块
  │       → 提取 parent_id → 从 LocalFileStore 加载父文档
  │       → 返回父文档列表
  │
  ├──→ [路径B] BM25 检索 (BM25Retriever)
  │       → jieba 中文分词
  │       → 基于所有父文档的关键词匹配
  │       → 返回 top-4 父文档
  │
  └──→ [融合] EnsembleRetriever
          → 权重: 向量 0.7 + BM25 0.3
          → 合并去重
          → 送入重排序器
```

### 6.2 自定义父文档检索器 (CustomParentDocumentRetriever)

**为什么不用原生 `ParentDocumentRetriever`？**

原生的 `ParentDocumentRetriever` 存在空召回问题（可能是版本兼容性 bug），因此项目实现了自定义检索器 `CustomParentDocumentRetriever`，继承自 `MultiVectorRetriever`。

**工作流程：**

1. 调用 `vectorstore.similarity_search(query, k=20)` 检索子块
2. 从匹配的子块中提取并去重 `parent_id`
3. 通过 `docstore.mget(parent_ids)` 批量加载父文档
4. 反序列化并校验（确保是 `Document` 类型且内容非空）
5. 返回父文档列表

**关键参数：**
- `search_kwargs = {"k": 20}`：向量检索返回 20 个子块
- `id_key = "parent_id"`：父子关联的元数据键

### 6.3 BM25 关键词检索

- **分词器**：`jieba.lcut`（中文分词）
- **检索对象**：所有父文档（从 `LocalFileStore` 全量加载）
- **返回数量**：`k = 4`
- **作用**：弥补向量检索在精确关键词匹配上的不足（如专有名词、编号等）

### 6.4 融合检索 (EnsembleRetriever)

- **融合方式**：加权融合
- **权重配置**：`[0.7, 0.3]`（向量检索 70%，BM25 30%）
- **设计考量**：向量检索权重更高，因为语义匹配在大多数场景下更可靠；BM25 作为补充，处理精确关键词匹配场景

---

## 7. 重排序（Rerank）

### 7.1 实现方式

使用阿里云百炼的 `qwen3-rerank` 模型，通过 HTTP API 进行远程调用。

### 7.2 实现类

`DashScopeRerank` 继承自 LangChain 的 `BaseDocumentCompressor`，作为 `ContextualCompressionRetriever` 的压缩器使用。

### 7.3 参数配置

| 参数 | 值 | 说明 |
|------|---|------|
| `model` | `qwen3-rerank` | 重排序模型 |
| `top_n` | `3` | 最终返回的文档数量 |
| `timeout` | `30s` | API 调用超时 |
| `return_documents` | `True` | 返回文档内容 |

### 7.4 降级策略

当 Rerank API 调用失败时（网络错误、响应格式异常等），系统会降级返回原始文档列表的前 `top_n` 个，保证检索链路不会因 Rerank 服务不可用而中断。

### 7.5 API 请求格式

```json
{
  "model": "qwen3-rerank",
  "input": {
    "query": "用户问题",
    "documents": ["文档1内容", "文档2内容", ...]
  },
  "parameters": {
    "return_documents": true,
    "top_n": 3
  }
}
```

---

## 8. 生成回答（Generation）

### 8.1 LLM 配置

| 参数 | 值 | 说明 |
|------|---|------|
| `model` | `qwen3.7-max` | 通义千问大模型 |
| `temperature` | `0.1` | 低温度，保证回答稳定性 |
| `timeout` | `300s` | 5 分钟超时 |
| `enable_search` | `True` | 启用模型内置搜索增强 |
| `base_url` | DashScope 兼容端点 | OpenAI 兼容接口 |

### 8.2 Prompt 设计

系统 Prompt 包含以下关键指令：

1. **角色设定**：畅星集团（SIS）TSU 车载终端技术专家
2. **回答约束**：
   - 严格基于参考文档回答，不编造内容
   - 引用来源文档名 (`file_name`) 和页码 (`page_number`)
   - 信息不完整时明确说明并给出合理推测
   - 无相关信息时明确回复「参考文档中未找到相关信息」
3. **语言适配**：回答语言与用户问题一致（中/日/英）

### 8.3 上下文格式化

`format_docs_with_metadata()` 函数将检索到的文档格式化为带元数据的上下文：

```
【来源文档】：xxx.pdf
【页码/章节】：3
【文档内容】：
...文档内容...
----------------------------------------
```

这使得 LLM 能够在回答中准确引用信息来源。

---

## 9. 同义词扩展机制

### 9.1 设计目的

解决公司内部缩写和全称之间的检索鸿沟。例如用户搜索 "DUF"，但文档中写的是 "DAQ Upload File"。

### 9.2 双向扩展

#### 查询端扩展（Query Expansion）

```python
# 用户输入: "DUF是什么"
# 扩展后:   "DUF OR DAQ Upload File 是什么"
```

在检索前对用户查询进行同义词扩展，使用 `OR` 连接缩写和全称。

#### 文档端增强（Document Enhancement）

```python
# 原始文档: "DAQ Upload File 用于..."
# 增强后:   "DAQ Upload File (DUF) 用于..."
```

在文档入库时，自动为全称添加缩写标注，提升双向匹配概率。

### 9.3 同义词词典

当前为硬编码的公司专用词典：

| 缩写 | 全称 |
|------|------|
| DUF | DAQ Upload File |
| DSF | DAQ Setting File |

词典支持双向映射，可自由扩展。

---

## 10. 增量更新（Diff Update）

### 10.1 设计目的

避免每次全量重建向量库，仅处理变更的文件，大幅提升索引更新效率。

### 10.2 更新策略

```
本地文件系统 ←→ 向量库元数据 对比
  │
  ├── 删除：向量库有但本地已不存在的文件
  │     → 删除对应的子块向量
  │     → 删除对应的父文档存储
  │
  ├── 修改：本地文件修改时间 > 向量库记录的修改时间
  │     → 先删除旧的子块向量和父文档
  │     → 重新解析、分割、索引
  │
  └── 新增：本地有但向量库中没有的文件
        → 解析、分割、索引
        → 存储父文档
```

### 10.3 变更检测

- 基于文件修改时间 (`file_mtime`) 判断文件是否变更
- 基于文件名 (`file_name`) 判断文件是否新增/删除
- 使用文件路径的 MD5 哈希作为 `parent_id` 前缀，避免路径特殊字符问题

---

## 11. 服务集成层

### 11.1 集成架构

RAG 能力通过以下层级集成到 Seki Agent 系统中：

```
前端 Chat 请求
  → AgentService (app/services/agent_service.py)
    → AgentRunner (app/services/agent_runner.py)
      → LangGraph Agent (app/services/langgraph_agent_factory.py)
        → LangChain Tool Adapter (app/services/langchain_tool_adapter.py)
          → RagAgentTool (app/services/agent_tools.py)
            → RagService (app/services/rag_service.py)
              → Legacy RAG 管线 (backend/legacy/)
```

### 11.2 RagService

`RagService` 是 RAG 能力的服务层封装：
- **懒加载**：首次调用时动态导入 Legacy 模块，避免启动时加载不必要的依赖
- **单例 QA Chain**：`_qa_chain` 在首次调用后缓存，后续请求复用
- **API Key 管理**：支持全局配置和临时 API Key 两种方式
- **可测试性**：支持注入自定义 `answerer` 用于单元测试

### 11.3 RagAgentTool

将 `RagService` 包装为 Agent 可调用的工具：
- 输入：用户问题（字符串）
- 输出：`AgentToolResult`，包含 `content`（回答文本）和 `data.sources`（来源信息）

### 11.4 LangChain Tool Adapter

将 `RagAgentTool` 转换为 LangChain `StructuredTool`：
- 工具名称：`rag`
- 工具描述：「回答公司业务、TSU/TBOX、项目文档相关问题。仅当用户询问公司业务或明确要求查知识库时使用。」
- Agent 根据工具描述自主决定是否调用 RAG

---

## 12. 配置参数汇总

### 12.1 环境变量

| 变量名 | 默认值 | 说明 |
|--------|-------|------|
| `SEKI_RAG_API_KEY` | - | RAG/LLM API Key（新服务层） |
| `RAG_API_KEY` | - | RAG API Key（Legacy 层） |
| `RAG_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | LLM API 端点 |
| `RAG_LLM_MODEL` | `qwen3.7-max` | 生成模型 |
| `RERANK_API_KEY` | - | Rerank API Key |
| `EMBEDDING_API_KEY` | - | Embedding API Key |
| `EMBEDDING_MODEL` | `text-embedding-v4` | Embedding 模型 |
| `IMAGE_CAPTION_API_KEY` | - | 图片描述 API Key |
| `IMAGE_CAPTION_LLM_MODEL` | `qwen3.5-flash` | 图片描述模型 |
| `TBOX_DOCS_DIR` | `backend/legacy/tbox_docs` | 知识库文档目录 |
| `PARENT_STORE_DIR` | `backend/legacy/parent_store` | 父文档存储目录 |
| `VECTOR_DB_DIR` | `backend/legacy/tbox_vector_db` | 向量库持久化目录 |

### 12.2 核心参数

| 参数 | 值 | 位置 |
|------|---|------|
| 子块 chunk_size | 300 | `rag.py`, `vector_db.py` |
| 子块 chunk_overlap | 50 | `rag.py`, `vector_db.py` |
| TXT chunk_size | 1000 | `vector_db.py` |
| TXT chunk_overlap | 200 | `vector_db.py` |
| Excel 行块大小 | 10 行 | `vector_db.py` |
| 向量检索 k | 20 | `rag.py` (CustomParentDocumentRetriever) |
| BM25 检索 k | 4 | `rag.py` |
| 融合权重 (向量:BM25) | 0.7 : 0.3 | `rag.py` |
| Rerank top_n | 3 | `rag.py` |
| LLM temperature | 0.1 | `rag.py` |
| LLM timeout | 300s | `rag.py` |

---

## 13. 设计亮点

### 13.1 多路召回融合

结合向量语义检索和 BM25 关键词检索两种互补的检索方式：
- **向量检索**擅长语义匹配（如 "车载终端" ↔ "TSU"）
- **BM25** 擅长精确匹配（如专有名词、编号、缩写）
- 通过 `EnsembleRetriever` 加权融合，兼顾两种场景

### 13.2 父子文档分割

采用 Parent-Child 分割策略，在检索精度和上下文完整性之间取得平衡：
- 子块（300 tokens）用于精确向量匹配
- 父文档（整页内容）保留完整上下文给 LLM
- 避免了小块检索导致上下文碎片化的问题

### 13.3 自定义父文档检索器

针对原生 `ParentDocumentRetriever` 的空召回问题，实现了 `CustomParentDocumentRetriever`：
- 直接控制子块检索 → 父文档加载的完整流程
- 批量加载父文档，提升效率
- 包含完善的调试日志和错误处理

### 13.4 多格式文档解析

通过 `unstructured` 库支持 PDF/PPT/Word/Excel/TXT 多种格式，并针对不同格式设计了差异化的聚合策略：
- PDF/PPT/Word：按页聚合，保留页码信息
- Excel：按行块聚合，每个块附带表头
- TXT：直接分割，不做父子拆分

### 13.5 图片文字提取

集成多模态模型 (`qwen3.5-flash`) 自动提取文档中图片的文字内容，避免图片信息在 RAG 流程中丢失。

### 13.6 同义词双向扩展

在查询端和文档端同时进行同义词处理：
- 查询端：扩展缩写为全称（提升召回率）
- 文档端：为全称添加缩写标注（提升匹配率）
- 特别适合公司内部术语和缩写的场景

### 13.7 增量更新机制

基于文件修改时间的差分更新策略，避免全量重建向量库：
- 自动检测新增、修改、删除的文件
- 仅处理变更部分，大幅节省索引时间
- 适合知识库文档频繁更新的场景

### 13.8 中文分词优化

为 BM25 检索器注册 `jieba` 中文分词器，显著提升中文关键词检索效果，避免默认空格分词在中文场景下的失效。

### 13.9 降级容错设计

- Rerank API 失败时降级返回原始排序
- 文档解析失败时回退到手动加载方法
- 向量库不存在时自动初始化

### 13.10 Agent 工具化集成

将 RAG 能力封装为 LangGraph Agent 的工具，Agent 可以根据用户意图自主决定是否调用知识库，实现 RAG 与通用对话的无缝切换。

---

## 14. 已知不足与改进方向

### 14.1 来源信息未完整传递

**问题**：`RagService` 返回的 `sources` 始终为空列表 `[]`，Legacy 管线中检索到的文档来源信息（文件名、页码）未能传递到新服务层。

**改进方向**：在 `rag_qa_chain` 返回结果中结构化输出来源文档信息，并在 `RagService._answer_with_rag()` 中解析和传递。

### 14.2 同义词词典硬编码

**问题**：`COMPANY_SYNONYMS` 词典硬编码在 `synonyms.py` 中，新增同义词需要修改代码。

**改进方向**：
- 将同义词词典外置为配置文件（如 JSON/YAML）或数据库表
- 提供管理界面或 API 进行动态维护

### 14.3 BM25 全量加载父文档

**问题**：BM25 检索器每次初始化时需要从 `LocalFileStore` 全量加载所有父文档，当文档量增大时会有性能问题。

**改进方向**：
- 引入 Elasticsearch 等支持 BM25 的搜索引擎
- 或采用稀疏向量检索（如 SPLADE）替代传统 BM25

### 14.4 向量检索仅使用 similarity_search

**问题**：自定义父文档检索器仅使用 `similarity_search`（余弦相似度），未利用 Chroma 支持的 MMR（最大边际相关性）等多样化检索策略。

**改进方向**：
- 引入 MMR 检索减少召回文档的冗余度
- 或支持可配置的检索策略切换

### 14.5 缺少查询改写（Query Rewriting）

**问题**：当前仅做同义词扩展，未对模糊查询、多意图查询进行改写或拆分。

**改进方向**：
- 引入 LLM 驱动的查询改写（如 HyDE、Multi-Query）
- 对复杂问题进行子问题拆分，分别检索后合并

### 14.6 缺少检索结果评估

**问题**：没有对检索结果的相关性进行评估或过滤，低相关性的文档可能进入 LLM 上下文，影响回答质量。

**改进方向**：
- 在 Rerank 后增加相关性阈值过滤
- 引入检索结果的置信度评分机制

### 14.7 文档分割粒度固定

**问题**：子块 `chunk_size=300` 和父文档按页聚合的策略是固定的，未根据文档类型或内容特征动态调整。

**改进方向**：
- 根据文档类型（技术文档 vs 表格 vs 代码）动态调整分割参数
- 引入语义分割（Semantic Chunking），根据内容语义边界进行切分

### 14.8 缺少对话历史上下文

**问题**：RAG 检索时仅使用当前用户问题，未结合对话历史进行上下文理解。

**改进方向**：
- 将对话历史中的关键信息融入检索查询
- 支持多轮对话中的指代消解（如 "它" → 具体实体）

### 14.9 Legacy 模块耦合

**问题**：新服务层通过动态 `importlib` 加载 Legacy 模块，存在模块耦合和调试困难的问题。Legacy 模块中的全局变量和 `print` 调试输出也不利于生产环境使用。

**改进方向**：
- 将 Legacy RAG 管线重构为标准 Python 包，通过正式 import 引入
- 将 `print` 调试输出替换为结构化日志（`logging` / `structlog`）
- 消除全局变量，改为依赖注入

### 14.10 缺少缓存机制

**问题**：相同问题的检索和生成结果不会被缓存，重复查询会重复消耗 API 调用。

**改进方向**：
- 引入语义缓存（Semantic Cache），对相似问题直接返回缓存结果
- 或引入精确缓存，对完全相同的问题跳过检索和生成

---

## 15. 文件清单

| 文件路径 | 职责 |
|---------|------|
| `backend/legacy/rag.py` | RAG 检索链构建、Prompt 设计、QA 链执行 |
| `backend/legacy/vector_db.py` | 文档解析、分割、向量索引、增量更新 |
| `backend/legacy/custom_parent_document_retriever.py` | 自定义父文档检索器 |
| `backend/legacy/rerank.py` | DashScope Rerank 重排序器 |
| `backend/legacy/synonyms.py` | 同义词词典与扩展逻辑 |
| `backend/app/services/rag_service.py` | RAG 服务层封装（懒加载 Legacy） |
| `backend/app/services/agent_tools.py` | RAG Agent 工具包装 (`RagAgentTool`) |
| `backend/app/services/langchain_tool_adapter.py` | LangChain StructuredTool 适配 |
| `backend/app/services/langgraph_agent_factory.py` | LangGraph Agent 构建（注入 RAG 工具） |
| `backend/app/services/langgraph_agent_runner.py` | LangGraph Agent 执行与事件流 |
| `backend/app/services/agent_runner.py` | Agent 运行器（路由到 RAG 工具） |
| `backend/app/services/agent_service.py` | Agent 服务入口 |
| `backend/app/core/config.py` | 全局配置（RAG 相关参数） |
