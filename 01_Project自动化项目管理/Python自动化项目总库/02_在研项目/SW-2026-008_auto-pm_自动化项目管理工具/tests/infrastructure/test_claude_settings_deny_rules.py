"""钉住 `.claude/settings.json` 的拒绝清单：谁删掉一条必需规则，这个测试就红（TD-SW008-196）。

背景：本机 Claude Code 的工具层原先几乎没有限制。拒绝规则（强推、`rm -rf`、`git reset --hard`、
改 `.claude/**`、改账本文件、改 Git 钩子）已经在 `.claude/settings.json` 里生效，但文件里的规则
只是“写在那里”，没有任何机器在盯：有人顺手删一条，没有门禁会发现。这里把必需规则列成清单，
删掉任何一条都会让本测试失败；要放开某条规则，必须同时改本测试，改动会出现在 PR 范围检查里，
被审计和用户看见。

诚实边界（与台账 TD-SW008-196 一致）：
- 拒绝规则按命令文字匹配，不是沙箱，挡不住换写法（例如 `python -c`）；
- 本测试只证明“规则还在清单里”，不证明“规则真的把某条命令拦下过”，那条记录要在用户机器上做。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# 必需的拒绝规则。新增规则可以直接追加；删除或改写其中任何一条，必须在本清单同步修改。
REQUIRED_DENY_RULES: tuple[str, ...] = (
    # 防止 agent 改自己的拒绝规则与钩子、账本数据库
    "Edit(/.claude/**)",
    "Edit(**/.auto-pm/continuity.db*)",
    "Edit(**/.git/hooks/**)",
    # 强推与删分支
    "Bash(git push --force *)",
    "Bash(git push -f *)",
    "Bash(git push * --force *)",
    "Bash(git push * -f *)",
    "Bash(git push * --delete *)",
    # 丢弃本地改动、递归删除（三种写法顺序）
    "Bash(git reset --hard *)",
    "Bash(rm -rf *)",
    "Bash(rm -fr *)",
    "Bash(rm -r -f *)",
    # 删除或改动仓库设置
    "Bash(gh repo delete *)",
    "Bash(gh repo edit *)",
)


def _settings_path() -> Path | None:
    """找到仓库根（含 `.git`）下的 `.claude/settings.json`；不在 Git 仓库里就返回 None。

    找得到仓库根却没有这个文件，要让测试失败（文件被删等于规则全没了），不能当作“没有就跳过”。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent / ".claude" / "settings.json"
    return None


def _deny_rules() -> list[str]:
    path = _settings_path()
    if path is None:
        pytest.skip("不在 Git 仓库内（例如交付包副本），无 .claude/settings.json 可核对")
    assert path.is_file(), f"{path} 不存在：整份拒绝规则丢失"
    data = json.loads(path.read_bytes().decode("utf-8"))
    deny = data.get("permissions", {}).get("deny")
    assert isinstance(deny, list), "permissions.deny 缺失或不是列表：拒绝规则整体丢失"
    return [str(rule) for rule in deny]


@pytest.mark.parametrize("rule", REQUIRED_DENY_RULES)
def test_required_deny_rule_is_still_present(rule: str) -> None:
    deny = _deny_rules()
    assert rule in deny, f"必需的拒绝规则被删：{rule}（要放开必须同时改本测试并说明理由）"


def test_deny_list_has_no_duplicate_or_blank_entries() -> None:
    deny = _deny_rules()
    assert all(rule.strip() for rule in deny), "拒绝清单里有空白规则"
    assert len(deny) == len(set(deny)), "拒绝清单里有重复规则"
