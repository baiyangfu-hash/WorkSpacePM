import tempfile

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def test_cli_prototype_flow():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Test prototype init CLI
        res = runner.invoke(cli, ["-w", tmp_dir, "prototype", "init", "--pid", "TEST-001"])
        assert res.exit_code == 0
        assert "原型脚手架初始化成功" in res.output

        # Test prototype check CLI
        res_check = runner.invoke(cli, ["-w", tmp_dir, "prototype", "check", "--pid", "TEST-001"])
        assert res_check.exit_code == 0
        assert "原型检查" in res_check.output

        # Test prototype bundle CLI
        res_bundle = runner.invoke(cli, ["-w", tmp_dir, "prototype", "bundle", "--pid", "TEST-001", "--version", "V1.0.0"])
        assert res_bundle.exit_code == 0
        assert "原型打包成功" in res_bundle.output
