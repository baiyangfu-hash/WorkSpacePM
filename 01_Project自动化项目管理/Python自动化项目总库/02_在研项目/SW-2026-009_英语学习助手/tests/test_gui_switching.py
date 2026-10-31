"""
GUI 切换与 QML Bridge 自动化联调测试脚本
"""
import sys
import os
import json

# 确保 src 目录在 sys.path
SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl
from ui.qml_bridge import QmlBridge

import shutil
from pathlib import Path

import pytest

import cefr_tagger
import course_manager
import services.database_manager as database_manager


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """联调测试读写的是 data/app.db 的临时副本，不能改动已入库的那份。"""
    copy = tmp_path / "app.db"
    shutil.copyfile(database_manager.DB_PATH, copy)
    monkeypatch.setattr(database_manager, "DB_PATH", str(copy))
    monkeypatch.setattr(cefr_tagger, "DB_PATH", str(copy))
    monkeypatch.setattr(course_manager, "DB_PATH", str(copy))
    monkeypatch.setattr(database_manager, "_db_manager_instance", None)
    yield
    manager = database_manager._db_manager_instance
    if manager is not None:
        manager.close()


def test_qml_bridge_and_switching():
    print("=" * 60)
    print("开始 GUI 场景切换与 QML Bridge 联调测试")
    print("=" * 60)

    # 1. 初始化 QGuiApplication (如果未初始化)
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv)

    # 2. 实例 QmlBridge
    bridge = QmlBridge()

    # 3. 测试场景列表获取
    scenarios_json = bridge.getScenariosJson()
    scenarios = json.loads(scenarios_json)
    assert len(scenarios) >= 20, f"场景数不足，实际: {len(scenarios)}"
    print(f"✅ 场景列表成功加载: {len(scenarios)} 个场景")

    # 4. 测试不同场景详情切换 (街头问路 vs 快餐得来速)
    detail1_json = bridge.getScenarioDetailJson(scenarios[0]["id"])
    detail1 = json.loads(detail1_json)
    assert "lines" in detail1 or "dialogue" in detail1, "场景1详情缺失对话行"
    print(f"✅ 场景1 [{scenarios[0]['title']}] 切换加载成功: {len(detail1.get('lines', []))} 行对话")

    # 查找“快餐得来速”或第 6 个场景
    drive_thru_id = None
    for s in scenarios:
        if "快餐" in s["title"] or "得来速" in s["title"] or "drive" in s["title_en"].lower():
            drive_thru_id = s["id"]
            break
    if not drive_thru_id:
        drive_thru_id = scenarios[5]["id"]

    detail2_json = bridge.getScenarioDetailJson(drive_thru_id)
    detail2 = json.loads(detail2_json)
    assert detail1["title"] != detail2["title"], "场景切换未返回不同内容"
    print(f"✅ 场景2 [{detail2.get('title')}] 切换加载成功: {len(detail2.get('lines', []))} 行对话")
    # 5. 测试背词卡片获取与 FSRS 评分记录
    card_json = bridge.getRandomVocabCardJson()
    card_data = json.loads(card_json)
    assert "word" in card_data, "背词卡片数据缺失 word 字段"
    print(f"✅ 随机背词卡片成功加载: [{card_data.get('word')}]")

    review_res = bridge.recordReviewJson(card_data.get('word'), "good", 2)
    assert "word" in json.loads(review_res), "FSRS 评分记录失败"
    print(f"✅ FSRS 评分记录成功提交: [{card_data.get('word')}] -> good")

    # 6. 测试自由切换 CEFR 目标等级 (A1 -> B1)
    lvl_res = bridge.setUserLevelJson("B1")
    prog_data = json.loads(lvl_res)
    assert prog_data.get("current_level") == "B1", "设置 CEFR 等级为 B1 失败"
    print("✅ CEFR 目标等级自由切换成功: [A1 -> B1]")
    # 5. 测试 QML Engine 视图载入
    engine = QQmlApplicationEngine()
    qml_dir = os.path.join(SRC_DIR, 'ui', 'qml')
    engine.addImportPath(qml_dir)
    engine.rootContext().setContextProperty("qmlBridge", bridge)

    main_qml = os.path.join(qml_dir, 'main.qml')
    engine.load(QUrl.fromLocalFile(main_qml))

    root_objs = engine.rootObjects()
    assert len(root_objs) > 0, "QML 根窗口加载失败"
    print("✅ QML 主窗口 main.qml 载入成功，全视图初始化完毕")

    print("\n🎉 GUI 场景切换与 QML Bridge 自动化联调测试全部通过！")


if __name__ == '__main__':
    test_qml_bridge_and_switching()
