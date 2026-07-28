"""
MCP Server 测试模块

使用 pytest 测试 MCP Server 的工具注册、设备管理和各工具包的核心功能。
通过 mock 模拟 Appium WebDriver，避免依赖真实设备。
"""

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image
from selenium.common.exceptions import NoSuchElementException


def _create_valid_screenshot_b64(width: int = 1080, height: int = 2400) -> str:
    """创建一个有效的截图 base64 编码字符串，用于测试。

    Args:
        width: 截图宽度（像素），默认 1080。
        height: 截图高度（像素），默认 2400。

    Returns:
        str: PNG 格式截图的 base64 编码字符串。
    """
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ============================================================
# 辅助函数：创建 mock WebDriver
# ============================================================

def _create_mock_driver() -> MagicMock:
    """创建一个模拟的 Appium WebDriver 实例。

    Returns:
        MagicMock: 模拟的 WebDriver 实例，预设了常用方法的返回值。
    """
    driver = MagicMock()
    driver.capabilities = {
        "platformName": "Android",
        "platformVersion": "14",
        "deviceName": "emulator-5554",
        "udid": "emulator-5554",
        "automationName": "UiAutomator2",
        "appPackage": "com.example.app",
        "appActivity": ".MainActivity",
    }
    driver.get_window_size.return_value = {"width": 1080, "height": 2400}
    driver.page_source = '<hierarchy><node text="Hello" bounds="[0,0][1080,2400]"/></hierarchy>'
    driver.get_screenshot_as_base64.return_value = _create_valid_screenshot_b64()
    return driver


# ============================================================
# 工具注册测试
# ============================================================

class TestToolRegistration:
    """MCP 工具注册功能测试"""

    def test_server_creates_successfully(self):
        """测试 MCP Server 实例能否成功创建"""
        from src.mobile_mcp.server import MobileAutomationServer

        with patch("src.mobile_mcp.server.settings") as mock_settings:
            mock_settings.APPIUM_HOST = "127.0.0.1"
            mock_settings.APPIUM_PORT = 4723
            mock_settings.APPIUM_BASE_PATH = "/wd/hub"
            mock_settings.DEVICE_CONFIG_PATH = "/nonexistent/devices.yaml"

            server = MobileAutomationServer(name="test-server")
            assert server is not None
            assert server.name == "test-server"

    def test_device_manager_initialization(self):
        """测试 DeviceManager 正确初始化"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager(appium_url="http://localhost:4723")
        assert dm._appium_url == "http://localhost:4723"
        assert len(dm._connections) == 0
        assert len(dm._device_configs) == 0

    def test_register_device_config(self):
        """测试设备预配置注册"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        dm.register_device_config(
            device_id="device_1",
            name="Android 14 Emulator",
            platform="Android",
            udid="emulator-5554",
            system_port=8200,
        )
        assert "device_1" in dm._device_configs
        assert dm._device_configs["device_1"].platform == "Android"
        assert dm._device_configs["device_1"].udid == "emulator-5554"

    def test_register_ios_device_config(self):
        """测试 iOS 设备预配置注册"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        dm.register_device_config(
            device_id="ios_1",
            name="iPhone 15",
            platform="iOS",
            udid="auto-device-id",
            wda_port=8100,
        )
        assert "ios_1" in dm._device_configs
        assert dm._device_configs["ios_1"].platform == "iOS"


# ============================================================
# 设备管理测试
# ============================================================

class TestDeviceManager:
    """设备管理器功能测试"""

    def test_connect_device_success(self):
        """测试成功连接移动设备"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        mock_driver = _create_mock_driver()

        with patch("src.mobile_mcp.tools.device.webdriver.Remote", return_value=mock_driver), \
             patch.object(dm, "_is_appium_running", return_value=True), \
             patch.object(dm, "_kill_uiautomator2"):
            result = dm.connect_device(platform="Android", device_name="emulator-5554")

        assert result["success"] is True
        assert "连接成功" in result["data"]["message"]

    def test_connect_device_already_connected(self):
        """测试重复连接设备返回已连接提示"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        mock_driver = _create_mock_driver()

        with patch("src.mobile_mcp.tools.device.webdriver.Remote", return_value=mock_driver), \
             patch.object(dm, "_is_appium_running", return_value=True), \
             patch.object(dm, "_kill_uiautomator2"):
            dm.connect_device(platform="Android", device_name="emulator-5554")
            result = dm.connect_device(platform="Android", device_name="emulator-5554")

        assert result["success"] is True
        assert "已存在连接" in result["data"]["message"]

    def test_connect_device_failure(self):
        """测试设备连接失败时的错误处理"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()

        with patch("src.mobile_mcp.tools.device.webdriver.Remote", side_effect=Exception("Connection refused")), \
             patch.object(dm, "_is_appium_running", return_value=True), \
             patch.object(dm, "_kill_uiautomator2"):
            result = dm.connect_device(platform="Android", device_name="bad_device")

        assert result["success"] is False
        assert "Connection refused" in result["data"]["error"]

    def test_disconnect_device_success(self):
        """测试断开设备连接"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        mock_driver = _create_mock_driver()

        with patch("src.mobile_mcp.tools.device.webdriver.Remote", return_value=mock_driver), \
             patch.object(dm, "_is_appium_running", return_value=True), \
             patch.object(dm, "_kill_uiautomator2"):
            dm.connect_device(platform="Android", device_name="emulator-5554")
            result = dm.disconnect_device("emulator-5554")

        assert result["success"] is True
        assert "已断开连接" in result["data"]["message"]

    def test_disconnect_device_not_connected(self):
        """测试断开未连接的设备"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        result = dm.disconnect_device("nonexistent")

        assert result["success"] is False
        assert "未连接" in result["data"]["message"]

    def test_get_device_info(self):
        """测试获取设备信息"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        mock_driver = _create_mock_driver()

        with patch("src.mobile_mcp.tools.device.webdriver.Remote", return_value=mock_driver), \
             patch.object(dm, "_is_appium_running", return_value=True), \
             patch.object(dm, "_kill_uiautomator2"):
            dm.connect_device(platform="Android", device_name="emulator-5554")
            result = dm.get_device_info("emulator-5554")

        assert result["success"] is True
        assert result["data"]["platform"] == "Android"
        assert result["data"]["screen_width"] == 1080

    def test_list_devices(self):
        """测试列出设备列表"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        dm.register_device_config(device_id="dev1", name="Device 1", platform="Android")
        dm.register_device_config(device_id="dev2", name="Device 2", platform="iOS")

        result = dm.list_devices()
        assert result["success"] is True
        assert len(result["data"]["configured"]) == 2
        assert len(result["data"]["connected"]) == 0

    def test_build_android_capabilities(self):
        """测试构建 Android Capabilities"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        dm.register_device_config(
            device_id="android_1",
            name="Pixel 7",
            platform="Android",
            udid="emulator-5554",
        )
        options = dm._build_capabilities("android_1")
        assert options is not None

    def test_build_ios_capabilities(self):
        """测试构建 iOS Capabilities"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        dm.register_device_config(
            device_id="ios_1",
            name="iPhone 15",
            platform="iOS",
            udid="auto-device-id",
        )
        options = dm._build_capabilities("ios_1")
        assert options is not None

    def test_build_default_capabilities(self):
        """测试无预配置时构建默认 Capabilities"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        options = dm._build_capabilities("unknown_device")
        assert options is not None

    def test_disconnect_all(self):
        """测试断开所有设备"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        mock_driver = _create_mock_driver()

        with patch("src.mobile_mcp.tools.device.webdriver.Remote", return_value=mock_driver), \
             patch.object(dm, "_is_appium_running", return_value=True), \
             patch.object(dm, "_kill_uiautomator2"):
            dm.connect_device(platform="Android", device_name="dev1")
            dm.connect_device(platform="Android", device_name="dev2")
            result = dm.disconnect_all()

        assert result["success"] is True
        assert result["data"]["disconnected_count"] == 2


# ============================================================
# UI 交互测试
# ============================================================

class TestUIToolkit:
    """UI 交互操作测试"""

    def _setup_toolkit(self):
        """创建带 mock driver 的 UIToolkit 实例。"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.ui import UIToolkit

        dm = DeviceManager()
        mock_driver = _create_mock_driver()
        dm._connections["test_device"] = mock_driver
        toolkit = UIToolkit(dm)
        return toolkit, mock_driver

    def test_tap_element_success(self):
        """测试通过定位策略点击元素"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element

        result = toolkit.tap_element("test_device", by="id", value="btn_login")
        assert result["success"] is True
        mock_element.click.assert_called_once()

    def test_tap_element_device_not_connected(self):
        """测试点击未连接设备"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.ui import UIToolkit

        dm = DeviceManager()
        toolkit = UIToolkit(dm)
        result = toolkit.tap_element("nonexistent", 540, 1200)
        assert result["success"] is False

    def test_tap_by_text_success(self):
        """测试通过文本点击"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element

        result = toolkit.tap_by_text("test_device", "登录")
        assert result["success"] is True
        mock_element.click.assert_called_once()

    def test_tap_by_text_not_found(self):
        """测试点击不存在的文本"""
        toolkit, mock_driver = self._setup_toolkit()
        from selenium.common.exceptions import NoSuchElementException
        mock_driver.find_element.side_effect = NoSuchElementException()

        result = toolkit.tap_by_text("test_device", "不存在")
        assert result["success"] is False

    def test_input_text_success(self):
        """测试向元素输入文本"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()
        mock_driver.find_element.return_value = mock_element

        result = toolkit.input_text("test_device", by="id", value="username_field", text="testuser")
        assert result["success"] is True
        mock_element.clear.assert_called_once()
        mock_element.send_keys.assert_called_once_with("testuser")

    def test_swipe_success(self):
        """测试滑动操作"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_driver.swipe.reset_mock()
        result = toolkit.swipe("test_device", 540, 2000, 540, 500)
        assert result["success"] is True
        # swipe 现在使用 driver.swipe()（W3C Actions API），不再走 execute_script
        mock_driver.swipe.assert_called_once_with(540, 2000, 540, 500, 500)

    def test_long_press_success(self):
        """测试长按操作"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_driver.execute_script.reset_mock()
        result = toolkit.long_press("test_device", 540, 1200, duration=1500)
        assert result["success"] is True
        # ensure_connected() 会先调用 getDeviceTime 做健康检查，再调用实际手势
        assert mock_driver.execute_script.call_count == 2
        mock_driver.execute_script.assert_called_with(
            "mobile: longClickGesture",
            {"x": 540, "y": 1200, "duration": 1500},
        )

    def test_press_key_back(self):
        """测试按下返回键"""
        toolkit, mock_driver = self._setup_toolkit()
        result = toolkit.press_key("test_device", "back")
        assert result["success"] is True
        mock_driver.press_keycode.assert_called_once_with(4)

    def test_press_key_home(self):
        """测试按下 Home 键"""
        toolkit, mock_driver = self._setup_toolkit()
        result = toolkit.press_key("test_device", "home")
        assert result["success"] is True
        mock_driver.press_keycode.assert_called_once_with(3)

    def test_press_key_invalid(self):
        """测试按下不支持的按键"""
        toolkit, mock_driver = self._setup_toolkit()
        result = toolkit.press_key("test_device", "invalid_key")
        assert result["success"] is False
        assert "不支持" in result["data"]["message"]

    def test_scroll_down(self):
        """测试向下滚动"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_driver.execute_script.reset_mock()
        result = toolkit.scroll("test_device", "down", 0.5)
        assert result["success"] is True
        # ensure_connected() 会先调用 getDeviceTime 做健康检查，再调用实际手势
        assert mock_driver.execute_script.call_count == 2
        mock_driver.execute_script.assert_called_with(
            "mobile: scrollGesture",
            {"direction": "down", "percent": 0.5},
        )

    def test_scroll_invalid_direction(self):
        """测试无效的滚动方向"""
        toolkit, mock_driver = self._setup_toolkit()
        result = toolkit.scroll("test_device", "diagonal")
        assert result["success"] is False

    def test_swipe_element_left(self):
        """测试元素内方向滑动（向左拖动 SeekBar）"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()
        mock_element.location = {"x": 100, "y": 500}
        mock_element.size = {"width": 800, "height": 60}
        mock_driver.find_element.return_value = mock_element
        mock_driver.swipe.reset_mock()

        result = toolkit.swipe_element(
            "test_device", by="accessibility_id", value="Media volume",
            direction="left", percent=0.8,
        )
        assert result["success"] is True
        # 验证调用了 driver.swipe，且起终点在元素范围内
        mock_driver.swipe.assert_called_once()
        call_args = mock_driver.swipe.call_args[0]
        start_x, start_y, end_x, end_y = call_args[:4]
        # 向左滑动：start_x > end_x（从右滑向左）
        assert start_x > end_x
        # y 坐标应在元素范围内
        assert 500 <= start_y <= 560

    def test_swipe_element_not_found(self):
        """测试元素内滑动时元素未找到"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_driver.find_element.side_effect = NoSuchElementException()

        result = toolkit.swipe_element(
            "test_device", by="id", value="nonexistent",
            direction="left",
        )
        assert result["success"] is False
        assert "未找到" in result["data"]["message"]

    def test_swipe_zero_distance(self):
        """测试零距离滑动被拒绝"""
        toolkit, mock_driver = self._setup_toolkit()
        result = toolkit.swipe("test_device", 100, 200, 100, 200)
        assert result["success"] is False
        assert "相同" in result["data"]["message"]

    def test_wait_for_element_success(self):
        """测试等待元素出现"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()
        mock_element.tag_name = "android.widget.Button"
        mock_element.text = "确定"
        mock_element.location = {"x": 100, "y": 200}
        mock_element.size = {"width": 200, "height": 50}
        mock_element.is_displayed.return_value = True
        mock_element.is_enabled.return_value = True
        mock_element.is_selected.return_value = False
        mock_element.get_attribute.return_value = "confirm_btn"

        with patch("src.mobile_mcp.tools.ui.WebDriverWait") as MockWait:
            MockWait.return_value.until.return_value = mock_element
            result = toolkit.wait_for_element(
                "test_device", {"by": "accessibility_id", "value": "btn_ok"}
            )

        assert result["success"] is True
        assert result["data"]["element"]["text"] == "确定"


# ============================================================
# 视觉工具测试
# ============================================================

class TestVisionToolkit:
    """视觉工具功能测试"""

    def _setup_toolkit(self):
        """创建带 mock driver 的 VisionToolkit 实例。"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.vision import VisionToolkit

        dm = DeviceManager()
        mock_driver = _create_mock_driver()
        dm._connections["test_device"] = mock_driver
        toolkit = VisionToolkit(dm)
        return toolkit, mock_driver

    def test_take_screenshot_success(self):
        """测试截图功能"""
        toolkit, mock_driver = self._setup_toolkit()

        # mock compress_screenshot 返回一个有效的小型 base64 图片
        tiny_b64 = _create_valid_screenshot_b64(width=10, height=10)
        with patch("src.mobile_mcp.tools.vision._compress_screenshot", return_value=tiny_b64):
            result = toolkit.take_screenshot("test_device")

        assert result["success"] is True
        assert "screenshot" in result["data"]

    def test_take_screenshot_device_not_connected(self):
        """测试未连接设备截图"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.vision import VisionToolkit

        dm = DeviceManager()
        toolkit = VisionToolkit(dm)
        result = toolkit.take_screenshot("nonexistent")
        assert result["success"] is False

    def test_get_ui_tree_compressed(self):
        """测试获取压缩后的 UI 树"""
        toolkit, mock_driver = self._setup_toolkit()

        with patch("src.mobile_mcp.tools.vision.compress_xml", return_value='{"compressed_tree": {}}'):
            result = toolkit.get_ui_tree("test_device", compress=True)

        assert result["success"] is True
        assert result["data"]["compressed"] is True
        assert result["data"]["format"] == "json"

    def test_get_ui_tree_raw(self):
        """测试获取原始 UI 树"""
        toolkit, mock_driver = self._setup_toolkit()
        result = toolkit.get_ui_tree("test_device", compress=False)

        assert result["success"] is True
        assert result["data"]["compressed"] is False
        assert result["data"]["format"] == "xml"


# ============================================================
# 断言工具测试
# ============================================================

class TestAssertToolkit:
    """断言工具功能测试"""

    def _setup_toolkit(self):
        """创建带 mock driver 的 AssertToolkit 实例。"""
        from src.mobile_mcp.tools.assertions import AssertToolkit
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        mock_driver = _create_mock_driver()
        dm._connections["test_device"] = mock_driver
        toolkit = AssertToolkit(dm)
        return toolkit, mock_driver

    def test_assert_text_visible_success(self):
        """测试文本可见性断言通过"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()

        with patch("src.mobile_mcp.tools.assertions.WebDriverWait") as MockWait:
            MockWait.return_value.until.return_value = mock_element
            result = toolkit.assert_text_visible("test_device", "登录", timeout=5)

        assert result["success"] is True
        assert "断言通过" in result["data"]["message"]

    def test_assert_text_visible_timeout(self):
        """测试文本可见性断言超时"""
        toolkit, mock_driver = self._setup_toolkit()
        from selenium.common.exceptions import TimeoutException

        with patch("src.mobile_mcp.tools.assertions.WebDriverWait") as MockWait:
            MockWait.return_value.until.side_effect = TimeoutException()
            result = toolkit.assert_text_visible("test_device", "不存在", timeout=3)

        assert result["success"] is False
        assert "断言失败" in result["data"]["message"]

    def test_assert_element_exists_success(self):
        """测试元素存在性断言通过"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_element = MagicMock()
        mock_element.text = "确定"
        mock_element.is_displayed.return_value = True
        mock_driver.find_element.return_value = mock_element

        result = toolkit.assert_element_exists(
            "test_device", {"by": "accessibility_id", "value": "btn_ok"}
        )
        assert result["success"] is True

    def test_assert_element_exists_not_found(self):
        """测试元素不存在断言失败"""
        toolkit, mock_driver = self._setup_toolkit()
        from selenium.common.exceptions import NoSuchElementException
        mock_driver.find_element.side_effect = NoSuchElementException()

        result = toolkit.assert_element_exists(
            "test_device", {"by": "xpath", "value": "//nonexistent"}
        )
        assert result["success"] is False

    def test_assert_page_contains_success(self):
        """测试页面内容断言通过"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_driver.page_source = '<node text="Welcome" bounds="[0,0][100,100]"/>'

        result = toolkit.assert_page_contains("test_device", "Welcome")
        assert result["success"] is True

    def test_assert_page_contains_failure(self):
        """测试页面内容断言失败"""
        toolkit, mock_driver = self._setup_toolkit()
        mock_driver.page_source = '<node text="Hello" bounds="[0,0][100,100]"/>'

        result = toolkit.assert_page_contains("test_device", "Goodbye")
        assert result["success"] is False

    def test_assert_device_not_connected(self):
        """测试设备未连接时的断言"""
        from src.mobile_mcp.tools.assertions import AssertToolkit
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        toolkit = AssertToolkit(dm)
        result = toolkit.assert_text_visible("nonexistent", "test")
        assert result["success"] is False
        assert "未连接" in result["data"]["message"]


# ============================================================
# 错误处理测试
# ============================================================

class TestErrorHandling:
    """MCP Server 错误处理测试"""

    def test_device_not_found(self):
        """测试设备未找到时的错误处理"""
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        result = dm.get_device_info("nonexistent")
        assert result["success"] is False
        assert "未连接" in result["data"]["message"]

    def test_ui_toolkit_device_not_connected(self):
        """测试 UI 操作时设备未连接"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.ui import UIToolkit

        dm = DeviceManager()
        toolkit = UIToolkit(dm)
        result = toolkit.tap_element("nonexistent", 0, 0)
        assert result["success"] is False

    def test_vision_toolkit_device_not_connected(self):
        """测试视觉操作时设备未连接"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.vision import VisionToolkit

        dm = DeviceManager()
        toolkit = VisionToolkit(dm)
        result = toolkit.get_ui_tree("nonexistent")
        assert result["success"] is False

    def test_assert_toolkit_device_not_connected(self):
        """测试断言操作时设备未连接"""
        from src.mobile_mcp.tools.assertions import AssertToolkit
        from src.mobile_mcp.tools.device import DeviceManager

        dm = DeviceManager()
        toolkit = AssertToolkit(dm)
        result = toolkit.assert_element_exists("nonexistent", {"by": "xpath", "value": "//test"})
        assert result["success"] is False

    def test_input_text_missing_selector_value(self):
        """测试 wait_for_element 缺少 value 字段"""
        from src.mobile_mcp.tools.device import DeviceManager
        from src.mobile_mcp.tools.ui import UIToolkit

        dm = DeviceManager()
        mock_driver = _create_mock_driver()
        dm._connections["test_device"] = mock_driver
        toolkit = UIToolkit(dm)

        result = toolkit.wait_for_element("test_device", {"by": "xpath"})
        assert result["success"] is False
        assert "缺少" in result["data"]["message"]
