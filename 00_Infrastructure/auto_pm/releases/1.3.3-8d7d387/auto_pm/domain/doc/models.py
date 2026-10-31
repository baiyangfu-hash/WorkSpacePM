"""Domain models for doc-as-code and self-auditing."""
from dataclasses import dataclass, field


@dataclass
class CliCommandDTO:
    name: str
    group: str
    doc: str
    args: list[str] = field(default_factory=list)
    file_source: str = ""

@dataclass
class BridgeMethodDTO:
    bridge_name: str
    method_name: str
    args: list[str] = field(default_factory=list)
    is_slot: bool = True
    is_signal: bool = False
    doc: str = ""

@dataclass
class GateRuleDTO:
    rule_id: str
    rule_name: str
    category: str
    doc: str

@dataclass
class DocCheckResult:
    check_id: str
    name: str
    passed: bool
    message: str
    detail: str = ""
