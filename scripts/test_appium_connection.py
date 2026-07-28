"""Appium 连接独立测试脚本。

用于在项目外独立验证 Appium + 模拟器的连接是否正常。
测试内容：连接设备 → 获取页面源 → 截图 → 断开连接。

使用方法:
    cd mcp-langgraph-agent
    python scripts/test_appium_connection.py

如需修改设备参数，直接编辑下方 DEVICE_CONFIG 字典。
"""

import base64
import os
import sys
import time

# 设备连接参数 — 请根据你的实际环境修改
DEVICE_CONFIG = {
    "platform": "Android",
    "device_name": "Pixel_7_API_34",
    "udid": "emulator-5554",
    "appium_port": 4723,
    "appPackage": "",       # 填入你的 App 包名，如 "com.android.settings"
    "appActivity": "",      # 填入你的 App Activity，如 ".Settings"
    "automationName": "UiAutomator2",
    "platformVersion": "14",
    "noReset": True,
    "newCommandTimeout": 300,
}


def test_appium_connection():
    """测试 Appium 连接、UI 树获取和截图功能。"""
    from appium import webdriver
    from appium.options.android import UiAutomator2Options

    print("=" * 60)
    print("Appium 连接测试")
    print("=" * 60)

    # 检查环境变量
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not android_home:
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Library", "Android", "sdk"),
            os.path.join(home, "Android", "Sdk"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                android_home = path
                os.environ["ANDROID_HOME"] = path
                os.environ["ANDROID_SDK_ROOT"] = path
                break

    print(f"[1/5] ANDROID_HOME: {android_home or '未设置'}")

    # 检查 Appium Server 是否运行（base-path 为 /wd/hub，status 接口在 /wd/hub/status）
    appium_url = f"http://127.0.0.1:{DEVICE_CONFIG['appium_port']}/wd/hub"
    try:
        from urllib.request import urlopen
        resp = urlopen(f"{appium_url}/status", timeout=3)
        print(f"[2/5] Appium Server: 运行中 (status={resp.status})")
    except Exception:
        print(f"[2/5] Appium Server: 未运行！请先启动: appium --address 127.0.0.1 --port {DEVICE_CONFIG['appium_port']} --base-path /wd/hub")
        return

    # 构建 Capabilities
    options = UiAutomator2Options()
    options.device_name = DEVICE_CONFIG["device_name"]
    options.udid = DEVICE_CONFIG["udid"]
    options.set_capability("systemPort", 8200)
    options.set_capability("noReset", DEVICE_CONFIG["noReset"])
    options.set_capability("newCommandTimeout", DEVICE_CONFIG["newCommandTimeout"])

    if DEVICE_CONFIG["appPackage"]:
        options.set_capability("appPackage", DEVICE_CONFIG["appPackage"])
        print(f"        appPackage: {DEVICE_CONFIG['appPackage']}")
    else:
        print("        appPackage: (空) — 将连接到当前桌面")

    if DEVICE_CONFIG["appActivity"]:
        options.set_capability("appActivity", DEVICE_CONFIG["appActivity"])
        print(f"        appActivity: {DEVICE_CONFIG['appActivity']}")
    else:
        print("        appActivity: (空)")

    # 连接设备
    print(f"[3/5] 正在连接设备: {DEVICE_CONFIG['udid']} ...")
    try:
        driver = webdriver.Remote(
            command_executor=appium_url,
            options=options,
        )
        print(f"      连接成功! session_id={driver.session_id}")
    except Exception as e:
        print(f"      连接失败: {e}")
        return

    try:
        # 获取页面源（UI 树）
        print("[4/5] 正在获取 UI 树...")
        page_source = driver.page_source

        # 使用 xml.etree.ElementTree 正确统计节点数
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(page_source)
            element_count = sum(1 for _ in root.iter())
        except ET.ParseError:
            element_count = 0

        print(f"      UI 树获取成功! 原始大小={len(page_source)} 字节, 节点数={element_count}")

        # 检查 App 是否已启动
        package_name = root.attrib.get('package', '') if element_count > 0 else ''
        # 遍历第一层子元素查找 package 属性
        if not package_name:
            for child in root:
                pkg = child.attrib.get('package', '')
                if pkg:
                    package_name = pkg
                    break

        if element_count < 5:
            print(f"      ⚠ 节点数过少，可能 App 未启动")
        else:
            print(f"      App 包名: {package_name or '(未识别)'}")

        if element_count < 3:
            print(f"      当前页面片段: {page_source[:500]}")

        # 截图
        print("[5/5] 正在截图...")
        screenshot_b64 = driver.get_screenshot_as_base64()
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        screenshot_path = os.path.join(screenshot_dir, f"test_{timestamp}.png")
        with open(screenshot_path, "wb") as f:
            f.write(base64.b64decode(screenshot_b64))
        print(f"      截图保存到: {screenshot_path}")

    except Exception as e:
        print(f"      操作失败: {e}")
    finally:
        # 断开连接
        try:
            driver.quit()
            print("\n连接已断开，测试完成!")
        except Exception:
            pass

    print("=" * 60)


if __name__ == "__main__":
    test_appium_connection()
