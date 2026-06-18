# Seki Agent 工程化改造文档

本文档目录用于沉淀 Seki Agent 从原型项目走向工程化落地的需求、设计、实施计划与验收标准。

当前阶段目标不是一次性重写项目，而是按阶段完成：

1. 明确业务需求、用户角色、核心流程和非功能指标。
2. 设计前后端分离、模块解耦、可测试、可部署的目标架构。
3. 在不破坏现有能力的前提下，逐步迁移到规范工程结构。
4. 为每个核心模块补充单元测试、接口测试和必要的集成测试。
5. 引入并发、异步任务、可观测性、部署和高可用能力。

## 已知现状

基于当前代码初步盘点，项目现状如下：

- 新框架后端：`backend/`，FastAPI 模块化单体。
- 新框架前端：`frontend/`，React + Vite + TypeScript。
- 工程化文档：`docs/`。
- 旧 Streamlit/LangGraph 原型源码保留在 `old/`（仅 `src/` 与 `parse_spi/`，旧数据与依赖快照已清理）。
- 新后端仍需复用的旧能力运行时文件已复制并收敛到 `backend/legacy/`。
- 运行数据默认位于 `data/`，不作为源码资产保留。
- 部署方式：Docker Compose。

## 文档清单

- [需求澄清清单](./requirements-questions.md)
- [正式需求文档](./requirements.md)
- [目标架构设计](./architecture.md)
- [API 设计](./api-design.md)
- [阶段性实施计划](./refactor-roadmap.md)
- [Agent 迁移计划](./agent-migration-plan.md)
- [当前上下文摘要](./current-context.md)
- [当前实现状态总览](./implementation-status.md)
- [文件结构说明](./file-structure.md)
- [使用说明书](./user-guide.md)

说明：`refactor-roadmap.md` 保留历史迭代记录；如果只想了解当前代码状态和下一步，
优先阅读 `implementation-status.md`、`file-structure.md`、`user-guide.md`。
