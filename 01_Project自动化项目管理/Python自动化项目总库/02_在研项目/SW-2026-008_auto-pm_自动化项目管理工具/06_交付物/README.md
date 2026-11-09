# auto-pm 自动化项目管理工具 - 交付物总览 (DEV-030 V2.2.0)

> **现行发布版本**：以 `00_Infrastructure/auto_pm/active_release.json` 为准（2026-11-04 记录为 `1.3.3-d563293`，发版 7.1，上一版 `1.3.3-d671611`）；不要把本页当版本真源。  
> **交付管理规范**：`DEV-030 (V2.2.0) 对内稳定 / 对外分发 双轨制`  
> **最近整理日期**：`2026-11-04`  
> **权威运行与交付基线**：`00_Infrastructure/auto_pm/releases/<active_release.json 里的 release_id>`  
> **交付完整性凭据**：`00_Infrastructure/auto_pm/deployment_manifest.json` 里该版本的条目（exact-tree 校验，不重复造双包）  
> **历史基线**：`V1.2.4-6699a5b`（2026-09-07）及更早的 `1.2.x` 只作历史记录。

---

## 1. 对内资产索引（本地开发、测试与 AI 协作）

工作空间内部文档保持固定标准命名，版本号在文件 Frontmatter 中维护：

| 文档类型 | 规范路径 | 适用角色与用途 |
| :--- | :--- | :--- |
| **用户操作指南** | [001_用户操作指南与排障手册_USER_GUIDE.md](001_用户操作指南与排障手册_USER_GUIDE.md) | 面向使用方的 6 大业务 SOP 与排障 FAQ |
| **版本发布说明** | [002_版本发布说明_RELEASE_NOTES.md](002_版本发布说明_RELEASE_NOTES.md) | 面向发布方的版本特性演进与放行签署记录（页首为 V7 系列，第 1～3 节是 V1.2.4 历史记录） |
| **测试验收规程** | [`05_收尾/003_测试策略与验收规程_TEST_PLAN.md`](../05_收尾/003_测试策略与验收规程_TEST_PLAN.md) | 面向 QA 的 20 维全景功能验收清单 (Checklist，1928+ passed) |
| **CLI 命令参考** | [`02_规划/009_CLI命令参考.md`](../02_规划/009_CLI命令参考.md) | 面向所有角色：29 个命令组、195 条命令的实测清单（V2.0，2026-11-04） |
| **架构详细设计** | [`02_规划/003_详细设计说明书_DSN.md`](../02_规划/003_详细设计说明书_DSN.md) | 面向研发人员的 Clean Architecture 5层架构代码地图 |

---

## 2. 对外分发与稳定发布说明

- **生产权威部署**：基于双槽稳定部署容器，当前生产激活槽位由 `active_release.json` 指向的 `00_Infrastructure/auto_pm/releases/<release_id>` 承载，上一版由 `previous_release.json` 指向，以 `deployment_manifest.json` 为凭据，不重复打包生成外部双包；
- **历史归档制品**：`V1.1.0` 历史分发包已安全归档至 `archive/V1.1.0_20260817/`，`V1.1.0` 历史发布说明已归档至 `archive/002_版本发布说明_RELEASE_NOTES_V1.1.0_20260817.md`。

```
06_交付物/
├── 001_用户操作指南与排障手册_USER_GUIDE.md
├── 002_版本发布说明_RELEASE_NOTES.md (页首 V7 系列，正文 1～3 节为 V1.2.4 历史)
├── README.md
└── archive/
    ├── 002_版本发布说明_RELEASE_NOTES_V1.1.0_20260817.md
    └── V1.1.0_20260817/
        ├── 01_分发程序_V1.1.0/
        ├── auto-pm_V1.1.0_Release_20260817.zip
        └── auto-pm_V1.1.0_Source_20260817.zip
```

> **线上开发协作提示**：具备 Git 仓库权限的研发人员，也可直接通过 `git clone <repo-url>` 进行分支拉取与协作。
