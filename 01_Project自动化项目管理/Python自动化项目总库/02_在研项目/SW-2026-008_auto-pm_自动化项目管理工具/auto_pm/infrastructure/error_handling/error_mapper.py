"""工控现场异常统一转译器 (IndustrialErrorMapper)。

面向工业自动化工程师现场排障，将底层 Python、Socket、Modbus 及 OS 异常
转译为带有现场明确排障操作指引的中文诊断文本。
"""

import socket
import struct
from typing import Any


class IndustrialErrorMapper:
    """工控现场异常统一转译器。"""

    @staticmethod
    def format_exception(e: BaseException | str) -> str:
        """将异常或错误字符串转译为面向现场电气工程师的中文诊断信息。

        Args:
            e: 异常实例或字符串

        Returns:
            排障指引文本
        """
        if isinstance(e, str):
            err_msg = e
            err_cls_name = "Error"
        else:
            err_msg = str(e)
            err_cls_name = type(e).__name__

        # 1. 连接被拒绝（WinError 10061 / ConnectionRefusedError / ECONNREFUSED）
        if (
            isinstance(e, ConnectionRefusedError)
            or "10061" in err_msg
            or "refused" in err_msg.lower()
        ):
            return "【通信拒绝】目标 PLC/设备未启动 Modbus TCP 监听服务或 502 端口被占用。"

        # 2. 通信超时（TimeoutError / socket.timeout / timed out）
        if (
            isinstance(e, (TimeoutError, socket.timeout))
            or "timed out" in err_msg.lower()
            or "10060" in err_msg
        ):
            return "【通信超时】目标设备未在指定时间内响应，请排查物理网线、IP 网段及防火墙配置。"

        # 3. 本地网卡不可用 / 无法分配所请求的地址（WinError 10049 / EADDRNOTAVAIL）
        if "10049" in err_msg or "cannot assign requested address" in err_msg.lower():
            return "【网卡不可用】指定的源网卡 IP 地址不存在或网络已断开，请重新选择物理网卡。"

        # 4. 连接被远端重置 / 断开（WinError 10054 / ConnectionResetError / ECONNRESET）
        if (
            isinstance(e, (ConnectionResetError, ConnectionAbortedError))
            or "10054" in err_msg
            or "reset by peer" in err_msg.lower()
        ):
            return (
                "【连接中断】PLC/远端设备主动重置或关闭了连接，可能由于超出最大连接数或设备重启。"
            )

        # 5. 主机/网络不可达（WinError 10065 / EHOSTUNREACH）
        if (
            "10065" in err_msg
            or "no route to host" in err_msg.lower()
            or "unreachable" in err_msg.lower()
        ):
            return "【网络不可达】无法路由至目标设备，请确认本机 IP 与 PLC 处于同一局域网/网关。"

        # 6. 数据解析与解包错误（struct.error / ValueError）
        if isinstance(e, struct.error) or "unpack requires a buffer" in err_msg.lower():
            return f"【数据解析错误】寄存器数据长度与解析格式不匹配：{err_msg}"

        # 7. 文件系统相关异常
        if isinstance(e, FileNotFoundError):
            return f"【文件不存在】未能定位到目标路径：{err_msg}"

        if isinstance(e, PermissionError):
            return (
                f"【权限不足】无法访问或修改指定文件，请检查文件是否被占用或需管理员权限：{err_msg}"
            )

        # 8. 配置缺失
        if isinstance(e, KeyError):
            return f"【配置缺失】缺少必要配置项：{err_msg}"

        # 9. 默认降级格式
        if err_msg:
            return f"【{err_cls_name}】{err_msg}"
        return f"【{err_cls_name}】发生未知工控执行异常"

    @staticmethod
    def to_bridge_response(e: BaseException | str, *, success: bool = False) -> dict[str, Any]:
        """将异常转译为 QML Bridge 标准返回字典。

        Args:
            e: 异常实例或错误信息
            success: 成功标识（默认 False）

        Returns:
            dict: {"success": False, "message": "..."}
        """
        return {
            "success": success,
            "message": IndustrialErrorMapper.format_exception(e),
        }
