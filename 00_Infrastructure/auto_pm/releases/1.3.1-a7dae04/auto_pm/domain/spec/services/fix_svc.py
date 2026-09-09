"""PLC-HMI 概念映射：SFB 库函数（规范修复（自动修复规范违规项））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from auto_pm.spec.core.checker_base import CheckResult
from auto_pm.spec.core.registry import SpecRegistry
from auto_pm.spec.core.scanner import SpecScanner

log = logging.getLogger(__name__)


@dataclass
class FixResult:
    check_id: str
    applied: bool
    message: str


_AUTO_FIXABLE_IDS = {"SHC-002", "SHC-007"}


def can_auto_fix(result: CheckResult) -> bool:
    return result.check_id in _AUTO_FIXABLE_IDS


class BoundedHealingTracker:
    def __init__(self, workspace: Path):
        pid = workspace.name.split('_')[0] if '_' in workspace.name else 'UNKNOWN'
        self.tracker_file = workspace / ".auto-pm" / f"retry_tracker_{pid}.json"

    def check_and_record(self) -> bool:
        if not self.tracker_file.parent.exists():
            self.tracker_file.parent.mkdir(parents=True, exist_ok=True)

        data = {"retries": 0, "last_reset": time.time()}
        if self.tracker_file.exists():
            try:
                data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        now = time.time()
        # Reset tracker every 24 hours
        if now - data.get("last_reset", 0) > 86400:
            data = {"retries": 0, "last_reset": now}

        if data["retries"] >= 3:
            return False # Exceeded 3 retries

        data["retries"] += 1
        self.tracker_file.write_text(json.dumps(data), encoding="utf-8")
        return True


class FixService:
    def __init__(self, workspace: Path, registry: SpecRegistry, scanner: SpecScanner) -> None:
        self.workspace = workspace
        self.registry = registry
        self.scanner = scanner

    def fix_all(
        self,
        results: list[CheckResult],
        dry_run: bool = False,
    ) -> list[FixResult]:
        fix_results: list[FixResult] = []
        fixable = [r for r in results if can_auto_fix(r)]
        if not fixable:
            return fix_results

        if not dry_run:
            tracker = BoundedHealingTracker(self.workspace)
            if not tracker.check_and_record():
                log.warning("Subagent bounded healing limit reached (>=3 retries). Escaping infinite loop.")
                return fix_results

        for result in fixable:
            handler = getattr(self, f"_fix_{result.check_id.replace('-', '_').lower()}", None)
            if handler:
                fix_results.append(handler(result, dry_run))

        if not dry_run and any(fr.applied for fr in fix_results):
            self.registry.save()

        return fix_results

    def _fix_shc_002(self, result: CheckResult, dry_run: bool) -> FixResult:
        version_match = re.search(r"文件版本:\s*(V?[\d.]+)", result.details)
        registry_match = re.search(r"注册表版本:\s*(V?[\d.]+)", result.details)
        file_match = re.search(r"文件:\s*(.+)$", result.details)
        if not (version_match and registry_match and file_match):
            return FixResult(check_id=result.check_id, applied=False, message="无法解析版本信息")

        file_version = version_match.group(1)
        registry_version = registry_match.group(1)
        file_path_str = file_match.group(1).strip()
        file_path = Path(file_path_str)

        if not file_path.exists():
            file_path = self.workspace / file_path_str
        if not file_path.exists():
            return FixResult(check_id=result.check_id, applied=False, message=f"文件不存在: {file_path_str}")

        norm_file = file_version.lstrip("Vv")
        norm_reg = registry_version.lstrip("Vv")

        if norm_file == norm_reg:
            return FixResult(check_id=result.check_id, applied=False, message="版本已一致，无需修复")

        spec_num_match = re.match(r"^(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?", file_path.stem)
        if not spec_num_match:
            return FixResult(check_id=result.check_id, applied=False, message="无法从文件名提取规范编号")

        spec_num = spec_num_match.group(0)
        spec_info = self.registry.get_spec(spec_num)
        if not spec_info:
            return FixResult(check_id=result.check_id, applied=False, message=f"规范 {spec_num} 不在注册表中")

        target_version = registry_version if registry_version.startswith("V") else f"V{registry_version}"

        if dry_run:
            return FixResult(
                check_id=result.check_id,
                applied=False,
                message=f"[预览] 更新frontmatter版本: {file_version} → {target_version}",
            )

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return FixResult(check_id=result.check_id, applied=False, message=f"读取文件失败: {e}")

        import yaml
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                fm_text = content[3:end].strip()
                try:
                    existing = yaml.safe_load(fm_text) or {}
                except yaml.YAMLError:
                    return FixResult(check_id=result.check_id, applied=False, message="frontmatter YAML解析失败")
                existing["version"] = target_version
                new_fm = yaml.dump(existing, allow_unicode=True, default_flow_style=False).strip()
                remaining = content[end + 3:].lstrip("\n")
                new_content = f"---\n{new_fm}\n---\n{remaining}"
            else:
                return FixResult(check_id=result.check_id, applied=False, message="frontmatter格式异常，缺少结束标记")
        else:
            new_fm_dict = {
                "spec_id": spec_info.spec_id or spec_num,
                "title": spec_info.title or file_path.stem,
                "version": target_version,
                "lifecycle": spec_info.lifecycle or "stable",
            }
            new_fm = yaml.dump(new_fm_dict, allow_unicode=True, default_flow_style=False).strip()
            new_content = f"---\n{new_fm}\n---\n{content}"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            return FixResult(check_id=result.check_id, applied=False, message=f"写入文件失败: {e}")

        return FixResult(
            check_id=result.check_id,
            applied=True,
            message=f"更新frontmatter版本: {file_version} → {target_version}",
        )

    def _fix_shc_007(self, result: CheckResult, dry_run: bool) -> FixResult:
        file_match = re.search(r"文件:\s*(.+)$", result.details)
        if not file_match:
            return FixResult(check_id=result.check_id, applied=False, message="无法解析文件路径")

        file_path_str = file_match.group(1).strip()
        file_path = Path(file_path_str)
        if not file_path.exists():
            file_path = self.workspace / file_path_str
        if not file_path.exists():
            return FixResult(check_id=result.check_id, applied=False, message=f"文件不存在: {file_path_str}")

        spec_num_match = re.match(r"^(?:SW|PM|PLC|PY|CODE|LSP|INT)-\d{3,4}(?:-\d{3})?", file_path.stem)
        if not spec_num_match:
            return FixResult(check_id=result.check_id, applied=False, message="无法从文件名提取规范编号")

        spec_num = spec_num_match.group(0)
        spec_info = self.registry.get_spec(spec_num)
        if not spec_info:
            return FixResult(check_id=result.check_id, applied=False, message=f"规范 {spec_num} 不在注册表中")

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return FixResult(check_id=result.check_id, applied=False, message=f"读取文件失败: {e}")

        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                fm_text = content[3:end].strip()
                try:
                    import yaml
                    existing = yaml.safe_load(fm_text) or {}
                except Exception:
                    log.warning("解析 frontmatter YAML 失败", exc_info=True)
                    existing = {}
                missing_fields = []
                for field_name in ("spec_id", "title", "version", "lifecycle"):
                    if field_name not in existing or not existing[field_name]:
                        missing_fields.append(field_name)
                if not missing_fields:
                    return FixResult(check_id=result.check_id, applied=False, message="frontmatter已完整")
        else:
            existing = {}
            missing_fields = ["spec_id", "title", "version", "lifecycle"]

        new_values = {
            "spec_id": spec_info.spec_id or spec_num,
            "title": spec_info.title or file_path.stem,
            "version": spec_info.version or "V1.0.0",
            "lifecycle": spec_info.lifecycle or "stable",
            "canonical_path": spec_info.canonical_path or "",
        }

        if dry_run:
            fields_to_add = {k: v for k, v in new_values.items() if k in missing_fields or k not in existing}
            return FixResult(
                check_id=result.check_id,
                applied=False,
                message=f"[预览] 补全frontmatter字段: {', '.join(fields_to_add.keys())}",
            )

        for k, v in new_values.items():
            if k not in existing or not existing[k]:
                existing[k] = v

        import yaml
        new_fm = yaml.dump(existing, allow_unicode=True, default_flow_style=False).strip()
        new_content = f"---\n{new_fm}\n---\n"

        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                new_content += content[end + 3:].lstrip("\n")
            else:
                new_content += content[3:]
        else:
            new_content += content

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except OSError as e:
            return FixResult(check_id=result.check_id, applied=False, message=f"写入文件失败: {e}")

        return FixResult(
            check_id=result.check_id,
            applied=True,
            message=f"补全frontmatter: {', '.join(missing_fields)}",
        )

    def _update_frontmatter_path(self, file_path: Path, new_canonical_path: str) -> None:
        if not file_path.exists() or not new_canonical_path:
            return
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return
        content = re.sub(
            r"canonical_path:\s*[\"']?[^\"'\n]+[\"']?",
            f'canonical_path: "{new_canonical_path}"',
            content,
            count=1,
        )
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            pass
