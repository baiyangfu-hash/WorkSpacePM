"""统一常量定义测试（M3-Iter7）

验证 auto_pm.core.constants 模块的常量和便捷函数。
"""

from __future__ import annotations

from auto_pm.application.core.constants import (
    BUSINESS_LINE_CODES,
    BUSINESS_LINE_LABELS,
    BUSINESS_LINE_OPTIONS,
    DEFAULT_TEMPLATE_NAME,
    EQUIPMENT_TYPE_CODES,
    EQUIPMENT_TYPE_LABELS,
    PHASE_CODES,
    PHASE_LABELS,
    PHASE_OPTIONS,
    PLC_VENDOR_CODES,
    PLC_VENDOR_OPTIONS,
    PROJECT_TYPE_CODES,
    PROJECT_TYPE_LABELS,
    STACK_CODES,
    STACK_OPTIONS,
    STACK_TEMPLATE_MAP,
    get_business_line_label,
    get_equipment_type_label,
    get_phase_label,
    get_project_type_label,
    get_template_name,
    is_valid_business_line,
)


class TestStackTemplateMap:
    """技术栈 → 模板名映射测试"""

    def test_stack_template_map(self) -> None:
        """技术栈到模板名的映射"""
        assert STACK_TEMPLATE_MAP["plc"] == "plc-standard-project"
        assert STACK_TEMPLATE_MAP["python"] == "python-tool"

    def test_get_template_name(self) -> None:
        """get_template_name 函数"""
        assert get_template_name("plc") == "plc-standard-project"
        assert get_template_name("python") == "python-tool"
        # 未知技术栈返回默认值
        assert get_template_name("unknown") == DEFAULT_TEMPLATE_NAME
        assert get_template_name("") == DEFAULT_TEMPLATE_NAME

    def test_default_template_name(self) -> None:
        """默认模板名常量"""
        assert DEFAULT_TEMPLATE_NAME == "unknown"


class TestBusinessLineOptions:
    """业务线选项测试"""

    def test_business_line_options(self) -> None:
        """业务线选项列表"""
        assert len(BUSINESS_LINE_OPTIONS) == 5
        # 验证所有业务线编码
        codes = [opt[0] for opt in BUSINESS_LINE_OPTIONS]
        assert "SW" in codes
        assert "DJ" in codes
        assert "ZD" in codes
        assert "XT" in codes
        assert "WX" in codes

    def test_business_line_codes(self) -> None:
        """业务线编码列表"""
        assert BUSINESS_LINE_CODES == ["SW", "DJ", "ZD", "XT", "WX"]

    def test_business_line_labels(self) -> None:
        """业务线编码到标签的映射"""
        assert BUSINESS_LINE_LABELS["SW"] == "SW 软件开发"
        assert BUSINESS_LINE_LABELS["DJ"] == "DJ 单机设备"

    def test_get_business_line_label(self) -> None:
        """get_business_line_label 函数"""
        assert get_business_line_label("SW") == "SW 软件开发"
        assert get_business_line_label("DJ") == "DJ 单机设备"
        # 未知编码返回编码本身
        assert get_business_line_label("UNKNOWN") == "UNKNOWN"

    def test_is_valid_business_line(self) -> None:
        """is_valid_business_line 函数"""
        assert is_valid_business_line("SW") is True
        assert is_valid_business_line("DJ") is True
        assert is_valid_business_line("UNKNOWN") is False
        assert is_valid_business_line("") is False


class TestStackOptions:
    """技术栈选项测试"""

    def test_stack_options(self) -> None:
        """技术栈选项列表"""
        assert len(STACK_OPTIONS) == 2
        codes = [opt[0] for opt in STACK_OPTIONS]
        assert "plc" in codes
        assert "python" in codes

    def test_stack_codes(self) -> None:
        """技术栈编码列表"""
        assert "plc" in STACK_CODES
        assert "python" in STACK_CODES


class TestPhaseOptions:
    """项目阶段选项测试"""

    def test_phase_options(self) -> None:
        """项目阶段选项列表"""
        assert len(PHASE_OPTIONS) == 6
        codes = [opt[0] for opt in PHASE_OPTIONS]
        assert "initiating" in codes
        assert "planning" in codes
        assert "developing" in codes
        assert "commissioning" in codes
        assert "production" in codes
        assert "archived" in codes

    def test_phase_codes(self) -> None:
        """项目阶段编码列表"""
        assert PHASE_CODES == ["initiating", "planning", "developing", "commissioning", "production", "archived"]

    def test_phase_labels(self) -> None:
        """项目阶段编码到标签的映射"""
        assert PHASE_LABELS["developing"] == "开发中"
        assert PHASE_LABELS["archived"] == "已归档"

    def test_get_phase_label(self) -> None:
        """get_phase_label 函数"""
        assert get_phase_label("developing") == "开发中"
        assert get_phase_label("UNKNOWN") == "UNKNOWN"


class TestV040MetadataOptions:
    """V0.4.0 项目元数据选项测试"""

    def test_project_type_options(self) -> None:
        """项目类型选项列表"""
        assert "single_machine" in PROJECT_TYPE_CODES
        assert "shared_library" in PROJECT_TYPE_CODES
        assert PROJECT_TYPE_LABELS["single_machine"] == "单机设备"
        assert get_project_type_label("line_project") == "自动化整线"

    def test_equipment_type_options(self) -> None:
        """设备类型选项列表"""
        assert "conveyor" in EQUIPMENT_TYPE_CODES
        assert "robot_cell" in EQUIPMENT_TYPE_CODES
        assert EQUIPMENT_TYPE_LABELS["conveyor"] == "输送设备"
        assert get_equipment_type_label("packaging") == "包装设备"

    def test_plc_vendor_options(self) -> None:
        """PLC 品牌选项列表"""
        assert "Siemens" in PLC_VENDOR_CODES
        assert "Mitsubishi" in PLC_VENDOR_CODES
        assert len(PLC_VENDOR_OPTIONS) >= 5


class TestNoDuplicateDefinitions:
    """验证关键模块不再重复定义常量"""

    def test_project_service_uses_constants(self) -> None:
        """ProjectService 使用 constants 而非硬编码"""
        # 检查 project_service.py 模块不再有硬编码的 template_map
        import inspect

        from auto_pm.application.core.project_service import ProjectService

        source = inspect.getsource(ProjectService)
        # 不应包含硬编码的 template_map 定义
        assert 'template_map = {"plc": "plc-standard"' not in source
        # 应通过 get_template_name 函数调用
        assert "get_template_name" in source

    def test_cli_project_uses_constants(self) -> None:
        """cli/project.py 使用 constants 而非硬编码"""
        import inspect

        from auto_pm.ui.cli import project as project_module

        source = inspect.getsource(project_module)
        # 不应包含硬编码的 template_map 定义
        assert 'template_map = {"plc": "plc-standard"' not in source
        # 应通过 get_template_name 函数调用
        assert "get_template_name" in source
