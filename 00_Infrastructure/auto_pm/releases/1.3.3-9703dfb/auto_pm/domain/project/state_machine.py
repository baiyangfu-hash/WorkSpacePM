"""项目域状态机规则。"""

from __future__ import annotations

from typing import Any

STATE_MACHINE_NODES: tuple[dict[str, str], ...] = (
    {"name": "需求澄清 (Draft)", "icon": "pencil-simple"},
    {"name": "方案评审 (Review)", "icon": "paper-plane-tilt"},
    {"name": "实施中 (Implementing)", "icon": "code"},
    {"name": "闭环归档 (Closed)", "icon": "check"},
)

STATUS_TO_NODE_INDEX: dict[str, int] = {
    "draft": 0,
    "submitted": 0,
    "under_review": 0,
    "approved": 1,
    "implementing": 2,
    "pending_acceptance": 2,
    "accepting": 2,
    "completed": 3,
    "closed": 3,
}


def build_change_state_machine(status: str) -> dict[str, Any]:
    """根据变更状态构建平台驾驶舱状态机视图。"""
    current_node = STATUS_TO_NODE_INDEX.get(status, 0)
    is_final = current_node == len(STATE_MACHINE_NODES) - 1
    nodes: list[dict[str, Any]] = []
    for index, node_def in enumerate(STATE_MACHINE_NODES):
        if index < current_node:
            node_status = "done"
        elif index == current_node:
            node_status = "done" if is_final else "active"
        else:
            node_status = "pending"
        nodes.append(
            {
                "name": node_def["name"],
                "icon": node_def["icon"],
                "status": node_status,
            }
        )
    total_nodes = len(STATE_MACHINE_NODES)
    progress = int((current_node / (total_nodes - 1)) * 100) if total_nodes > 1 else 0
    return {
        "current_node": current_node,
        "current_node_name": STATE_MACHINE_NODES[current_node]["name"],
        "progress": progress,
        "nodes": nodes,
    }
