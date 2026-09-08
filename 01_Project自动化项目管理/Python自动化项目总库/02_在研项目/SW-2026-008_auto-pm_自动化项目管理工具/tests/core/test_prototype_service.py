import os
import tempfile

from auto_pm.core.prototype_service import PrototypeService


def test_prototype_init_and_bundle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        service = PrototypeService(tmp_dir)

        # Test init
        init_res = service.init(tmp_dir, template="hmi")
        assert init_res.success is True
        assert os.path.exists(init_res.output_path)

        # Test bundle
        bundle_res = service.bundle(tmp_dir, version="V1.0.0")
        assert bundle_res.success is True
        assert os.path.exists(bundle_res.output_path)
        assert "V1.0.0" in bundle_res.output_path

def test_prototype_check():
    with tempfile.TemporaryDirectory() as tmp_dir:
        service = PrototypeService(tmp_dir)
        service.init(tmp_dir, template="industrial-hmi")

        check_res = service.check(tmp_dir)
        assert check_res.passed is True
        assert len(check_res.errors) == 0


def test_prototype_detects_broken_link_and_missing_func():
    with tempfile.TemporaryDirectory() as tmp_dir:
        service = PrototypeService(tmp_dir)
        service.init(tmp_dir, template="industrial-hmi")

        html_path, _, js_path = service.locate_prototype_sources(tmp_dir)
        assert html_path is not None

        # 故意注入死链与未定义函数
        with open(html_path, "a", encoding="utf-8") as f:
            f.write('<button onclick="goPage(\'nonexistent_page\')">Broken Link</button>')
            f.write('<button onclick="undefinedCustomFunc()">Undefined Func</button>')

        check_res = service.check(tmp_dir)
        assert check_res.passed is False
        assert any("nonexistent_page" in err for err in check_res.errors)
        assert any("undefinedCustomFunc" in err for err in check_res.errors)

