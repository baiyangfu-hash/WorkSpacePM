---
spec_id: "CODES"
project_id: "SW-2026-008"
title: "auto-pm 报警代码表（脚本生成）"
---

# 报警代码表

> 本页由 `scripts/command_catalog.py` 生成，不要手改。
> 生成于提交 `68a6402fe4e9`。**本页可能落后**：之后改过命令或代码而没人重跑脚本，页上就是旧的；要最新的，运行 `python scripts/command_catalog.py --print`，以它的输出为准。
> 只收源码里真会报出来的代码（作为参数、字典值或返回值出现）；注释和文档字符串里提到的不算。“提示语”取自报出这个代码的同一处，看不懂时按“出在哪”去读源码。

## 检查代码（41 个）

| 代码 | 出在哪 | 提示语 |
|---|---|---|
| `CHK-000` | `auto_pm/application/delivery/verifier.py` | ZIP 文件不存在；ZIP 文件损坏 |
| `CHK-001` | `auto_pm/application/delivery/verifier.py` | 文件数正常；文件数过多；文件数过少 |
| `CHK-002` | `auto_pm/application/delivery/verifier.py` | ZIP 大小可接受；ZIP 大小正常；ZIP 过大；ZIP 过小 |
| `CHK-003` | `auto_pm/application/delivery/verifier.py` | exe 大小正常；exe 缺失；exe 过大；exe 过小 |
| `CHK-004` | `auto_pm/application/delivery/verifier.py` | _internal 文件数；_internal 缺失 |
| `CHK-005` | `auto_pm/application/delivery/verifier.py` | 文档文件数正常；文档文件数过少 |
| `CHK-006` | `auto_pm/application/delivery/verifier.py` | 一级目录不完整；一级目录完整 |
| `DOC-001` | `auto_pm/application/core/doc_services.py` | USER_GUIDE 缺少以下 CLI 分组说明: …；已覆盖全量 … 组 CLI 命令 |
| `DOC-004` | `auto_pm/application/core/doc_services.py` | pyproject=…，现役发布 … 的 version=…；无法比对：…（pyproject=…）；无法比对：读不到 pyproject.toml 的 [project] version；版本不一致：pyproject=…，现役发布 … 的 version=… |
| `LINT-001` | `auto_pm/ui/cli/spec.py` | workspace_root 路径过期 |
| `LINT-002` | `auto_pm/ui/cli/spec.py` | 孤立规范文件（未在 registry 注册） |
| `LINT-003` | `auto_pm/ui/cli/spec.py` | […] canonical_path 对应文件不存在（路径漂移） |
| `LINT-004` | `auto_pm/ui/cli/spec.py` | […] frontmatter 缺少必要字段: …（或其别名 …）；[…] 不是合法 UTF-8，无法检查 YAML frontmatter；[…] 缺少 YAML frontmatter |
| `LINT-005` | `auto_pm/ui/cli/spec.py` | […] 目录编号 …_ 重复 |
| `RP-001` | `auto_pm/application/core/role_pack_service.py` | 找不到角色库或里面没有角色包：…；缺少 … |
| `RP-002` | `auto_pm/application/core/role_pack_service.py` | role.json 不是合法 JSON：…；role.json 缺少键 …；role.json 顶层必须是对象 |
| `RP-003` | `auto_pm/application/core/role_pack_service.py` | role.json 的 id 是 …，与目录名不一致；角色号只能用小写字母、数字和连字符，不能含冒号（Windows 目录名与 AUTO_PM_AGENT 分段都不允许） |
| `RP-004` | `auto_pm/application/core/role_pack_service.py` | SKILL.md 的 name 是 …，应为 …；SKILL.md 缺少 description |
| `RP-005` | `auto_pm/application/core/role_pack_service.py` | 旧名 … 已被 … 认领 |
| `RP-006` | `auto_pm/application/core/role_pack_service.py` | 找不到 spec_registry.json，规范编号未核对；规范 … 不在 spec_registry.json 里 |
| `RP-007` | `auto_pm/application/core/role_pack_service.py` | … 里的指针 … 找不到 |
| `RP-008` | `auto_pm/application/core/role_pack_service.py` | legacy.mode … 不认识，只认 …；refs/… 缺失（旧技能里有）；role.json 的 legacy 必须是对象；… 与旧技能不一致；找不到旧技能目录 .trae/skills，与旧技能的一致性未核对；旧技能 … 不存在；路径写错请改正，已退役请在 role.json 的 legacy 里写 "retired": true；旧技能的 refs 目录 … 不存在；路径写错请改正，已退役请写 retired；旧技能里找不到章节 …；正文与旧技能 … 不逐字一致；正文没有逐字包含旧技能从 … 起的内容 |
| `RP-009` | `auto_pm/application/core/role_pack_service.py` | … 不是合法 UTF-8（第 … 字节处），文件已损坏；… 第 … 行有乱码特征 …（UTF-8 被当成别的编码存过） |
| `SHC-000` | `auto_pm/domain/spec/services/check_svc.py` | 注册表文件不存在或格式错误: … |
| `SHC-001` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … 存在重复文件 |
| `SHC-002` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … 版本不一致 |
| `SHC-003` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … 主动引用了已废弃规范 … |
| `SHC-004` | `auto_pm/domain/spec/core/checker_base.py` | 索引文件中列出的规范文件不存在: … |
| `SHC-005` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … 未在注册表中登记 |
| `SHC-006` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … 的Markdown链接指向不存在的文件: …；规范 … 的Obsidian链接指向不存在的文件: …；规范 … 链接了已废弃规范 … |
| `SHC-007` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … frontmatter缺少必填字段；规范 … 缺少frontmatter |
| `SHC-008` | `auto_pm/domain/spec/core/checker_base.py` | 规则文件引用了已废弃规范 …；规则文件引用了未注册规范 …；规则文件引用的规范路径无效: … |
| `SHC-009` | `auto_pm/domain/spec/core/checker_base.py` | PM_SESSION markdown链接目标不存在: …；PM_SESSION 引用的路径不存在: … |
| `SHC-010` | `auto_pm/domain/spec/core/checker_base.py` | 规范 … 交叉引用目标不存在: … |
| `SHC-011` | `auto_pm/domain/spec/core/checker_base.py` | … 未找到版本号；… 版本号不一致 |
| `SHC-012` | `auto_pm/domain/spec/core/checker_base.py` | 未找到 junit xml 测试结果文件；测试通过数不一致: §3声明 … vs junit xml … |
| `SHC-013` | `auto_pm/domain/spec/core/checker_base.py` | PM_SESSION §8 缺少验证状态标注 |
| `SHC-014` | `auto_pm/domain/spec/core/checker_base.py` | PM_SESSION §4 缺少必需文档索引: …；§4 文档索引路径无效: … → … |
| `SHC-015` | `auto_pm/domain/spec/core/checker_base.py` | 编号 … 存在跨前缀冲突 |
| `SHC-016` | `auto_pm/domain/spec/core/checker_base.py` | … 存在规范漂移警告 |
| `SHC-017` | `auto_pm/domain/spec/core/checker_base.py` | … … 漂移：文档缺失真源值 … |

## 约束编号（10 个）

`constraint check` 报的编号，取自每条约束定义文件的 id 和 name。哪几条机器真查、哪几条跳过，不在本页判断。

| 编号 | 定义文件 | 名字 |
|---|---|---|
| `CST-CHG-001` | `auto_pm/domain/constraint/definitions/change_cli_only.yaml` | 变更单必须通过 CLI 创建 |
| `CST-CHG-002` | `auto_pm/domain/constraint/definitions/change_dual_track.yaml` | 双轨变更通道分类规范 |
| `CST-EDIT-001` | `auto_pm/domain/constraint/definitions/edit_tool_protocol.yaml` | 遵循 Edit 工具微操协议 |
| `CST-ENV-001` | `auto_pm/domain/constraint/definitions/venv_activated.yaml` | 命令执行需激活虚拟环境 |
| `CST-FILE-001` | `auto_pm/domain/constraint/definitions/file_no_python_write.yaml` | 禁止 Python 脚本直接写磁盘 |
| `CST-FILE-002` | `auto_pm/domain/constraint/definitions/file_encoding_integrity.yaml` | 文件编码完整性 |
| `CST-NAME-001` | `auto_pm/domain/constraint/definitions/naming_no_version_suffix.yaml` | 文件命名禁止版本号后缀 |
| `CST-QUAL-001` | `auto_pm/domain/constraint/definitions/pre_commit_hooks.yaml` | 提交前强制通过静态门禁 |
| `CST-SKILL-001` | `auto_pm/domain/constraint/definitions/skill_change_requires_chg.yaml` | 技能变更必须通过 CHG 流程 |
| `CST-TEST-001` | `auto_pm/domain/constraint/definitions/gui_visible_mode.yaml` | GUI 测试强制默认可见模式 |
