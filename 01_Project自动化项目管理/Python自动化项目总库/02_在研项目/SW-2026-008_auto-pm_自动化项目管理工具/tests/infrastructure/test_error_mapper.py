"""Unit tests for IndustrialErrorMapper."""

import struct

from auto_pm.infrastructure.error_handling.error_mapper import IndustrialErrorMapper


def test_format_connection_refused():
    err = ConnectionRefusedError("[WinError 10061] No connection could be made")
    msg = IndustrialErrorMapper.format_exception(err)
    assert "【通信拒绝】" in msg
    assert "502" in msg


def test_format_timeout():
    err = TimeoutError("The read operation timed out")
    msg = IndustrialErrorMapper.format_exception(err)
    assert "【通信超时】" in msg
    assert "物理网线" in msg

    sock_err = TimeoutError("timed out")
    msg_sock = IndustrialErrorMapper.format_exception(sock_err)
    assert "【通信超时】" in msg_sock


def test_format_invalid_network_interface():
    err = OSError("[WinError 10049] The requested address is not valid in its context")
    msg = IndustrialErrorMapper.format_exception(err)
    assert "【网卡不可用】" in msg


def test_format_connection_reset():
    err = ConnectionResetError("[WinError 10054] An existing connection was forcibly closed")
    msg = IndustrialErrorMapper.format_exception(err)
    assert "【连接中断】" in msg


def test_format_unreachable():
    err = OSError("[WinError 10065] A socket operation was attempted to an unreachable host")
    msg = IndustrialErrorMapper.format_exception(err)
    assert "【网络不可达】" in msg


def test_format_struct_error():
    err = struct.error("unpack requires a buffer of 4 bytes")
    msg = IndustrialErrorMapper.format_exception(err)
    assert "【数据解析错误】" in msg


def test_format_file_errors():
    fnf = FileNotFoundError("config.json not found")
    msg_fnf = IndustrialErrorMapper.format_exception(fnf)
    assert "【文件不存在】" in msg_fnf

    perm = PermissionError("Access is denied")
    msg_perm = IndustrialErrorMapper.format_exception(perm)
    assert "【权限不足】" in msg_perm


def test_format_key_error():
    ke = KeyError("plc_type")
    msg_ke = IndustrialErrorMapper.format_exception(ke)
    assert "【配置缺失】" in msg_ke


def test_format_string_input():
    msg = IndustrialErrorMapper.format_exception("Connection refused by peer")
    assert "【通信拒绝】" in msg


def test_to_bridge_response():
    resp = IndustrialErrorMapper.to_bridge_response(TimeoutError("timed out"))
    assert resp["success"] is False
    assert "【通信超时】" in resp["message"]
