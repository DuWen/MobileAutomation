"""XML 压缩工具模块。

专门用于压缩 Appium 无障碍树 XML（Accessibility Tree），
通过深度截断、属性过滤和冗余容器移除等策略，
实现 95%+ 的 Token 压缩率。使用 xml.etree.ElementTree 进行可靠的 XML 解析。
"""

import json
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


# 需要保留的 XML 属性白名单
_KEEP_ATTRIBUTES: Set[str] = {
    'class',
    'text',
    'bounds',
    'clickable',
    'enabled',
    'focused',
    'content-desc',
    'package',
    'resource-id',
    'checkable',
    'checked',
    'selected',
    'scrollable',
    'long-clickable',
    'password',
}

# 需要移除的冗余容器类名
_REDUNDANT_CONTAINERS: Set[str] = {
    'android.widget.FrameLayout',
    'android.widget.LinearLayout',
    'android.widget.RelativeLayout',
    'android.view.ViewGroup',
    'android.view.View',
    'android.widget.ScrollView',
    'android.widget.HorizontalScrollView',
    'androidx.constraintlayout.widget.ConstraintLayout',
    'androidx.cardview.widget.CardView',
    'android.app.ActionBar$Tab',
    'android.widget.Toolbar',
    'android.widget.ActionMenuView',
    'com.android.internal.view.menu.ActionMenuItemView',
    'android.support.v7.widget.LinearLayoutCompat',
    'android.support.v7.widget.RecyclerView',
    'androidx.recyclerview.widget.RecyclerView',
    'android.widget.ListView',
    'android.widget.GridView',
    'android.widget.TableLayout',
    'android.widget.TableRow',
}

# 需要保留的交互式容器（即使类名在冗余列表中也不移除）
_INTERACTIVE_CONTAINERS: Set[str] = {
    'android.widget.ScrollView',
    'android.widget.HorizontalScrollView',
    'androidx.recyclerview.widget.RecyclerView',
    'android.support.v7.widget.RecyclerView',
}


def _filter_attributes(attrs: Dict[str, str]) -> Dict[str, str]:
    """过滤属性，仅保留白名单中的属性。

    Args:
        attrs: 原始属性字典

    Returns:
        过滤后的属性字典
    """
    return {k: v for k, v in attrs.items() if k in _KEEP_ATTRIBUTES}


def _is_redundant_container(
    class_name: str,
    attrs: Dict[str, str],
    child_count: int,
) -> bool:
    """判断是否为冗余容器节点。

    冗余容器判定条件：
    1. 类名在冗余容器列表中
    2. 不包含交互属性（不可点击、不可滚动等）
    3. 子节点数量不超过 1 个

    Args:
        class_name: 节点类名
        attrs: 节点属性字典
        child_count: 子节点数量

    Returns:
        是否为冗余容器
    """
    # 交互式容器保留
    if class_name in _INTERACTIVE_CONTAINERS:
        return False

    # 不在冗余列表中则不处理
    if class_name not in _REDUNDANT_CONTAINERS:
        return False

    # 检查是否包含交互属性
    is_clickable = attrs.get('clickable', 'false').lower() == 'true'
    is_checkable = attrs.get('checkable', 'false').lower() == 'true'
    is_scrollable = attrs.get('scrollable', 'false').lower() == 'true'
    is_long_clickable = attrs.get('long-clickable', 'false').lower() == 'true'
    has_text = bool(attrs.get('text', '').strip())

    # 有交互属性或文本内容的保留
    if is_clickable or is_checkable or is_scrollable or is_long_clickable or has_text:
        return False

    # 有多个子节点的容器保留（可能是重要的布局结构）
    if child_count > 1:
        return False

    return True


def _node_to_dict(
    node: Dict[str, Any],
    current_depth: int,
    max_depth: int,
    max_children: int,
) -> Dict[str, Any] | None:
    """递归将 XML 节点转换为精简字典。

    递归遍历 XML 节点树，应用深度截断、属性过滤和冗余容器移除策略。
    冗余容器判断使用原始子节点数（而非压缩后的），避免子节点被递归
    移除后导致父容器误判为无子节点而整个子树丢失。

    Args:
        node: XML 节点字典（包含 tag, attrs, children 等字段）
        current_depth: 当前递归深度
        max_depth: 最大允许深度
        max_children: 每个节点最大子节点数

    Returns:
        精简后的节点字典，如果该节点被过滤则返回 None
    """
    # 深度截断检查
    if current_depth > max_depth:
        return None

    # 提取并过滤属性
    attrs = node.get('attrs', {})
    filtered_attrs = _filter_attributes(attrs)
    class_name = filtered_attrs.get('class', '')

    # 判断冗余时使用原始子节点数，防止子节点被递归移除后父容器误判
    original_children = node.get('children', [])
    if _is_redundant_container(class_name, filtered_attrs, len(original_children)):
        # 冗余容器：跳过自身，直接递归处理子节点并提升
        promoted: List[Dict[str, Any]] = []
        for child in original_children[:max_children]:
            child_result = _node_to_dict(
                child,
                current_depth,  # 深度不递增，因为当前节点被跳过
                max_depth,
                max_children,
            )
            if child_result is not None:
                promoted.append(child_result)

        if len(promoted) == 1:
            return promoted[0]
        elif len(promoted) > 1:
            # 多个子节点无法合并提升，返回 None 让上层处理
            # 但要确保子节点不丢失：包装到一个保留的容器中
            return {
                'class': class_name,
                'children': promoted,
            }
        return None

    # 非冗余容器：正常递归处理子节点
    processed_children: List[Dict[str, Any]] = []
    for child in original_children[:max_children]:
        child_result = _node_to_dict(
            child,
            current_depth + 1,
            max_depth,
            max_children,
        )
        if child_result is not None:
            processed_children.append(child_result)

    # 构建结果节点
    result: Dict[str, Any] = {
        'class': filtered_attrs.get('class', ''),
    }

    # 只添加非空的属性
    for key in ('text', 'bounds', 'content-desc', 'package', 'resource-id'):
        value = filtered_attrs.get(key, '')
        if value:
            result[key] = value

    # 添加布尔属性
    for key in ('clickable', 'enabled', 'focused', 'checkable', 'checked',
                'selected', 'scrollable', 'long-clickable', 'password'):
        value = filtered_attrs.get(key, 'false')
        if value == 'true':
            result[key] = True

    # 添加子节点
    if processed_children:
        result['children'] = processed_children

    return result


def _parse_xml_to_tree(xml_str: str) -> Dict[str, Any] | None:
    """使用 xml.etree.ElementTree 解析 XML 为节点树。

    替代之前不可靠的正则解析方式，使用 Python 标准库的 XML 解析器
    正确处理嵌套结构、自闭合标签和属性值转义。

    Args:
        xml_str: XML 字符串

    Returns:
        节点树字典，解析失败返回 None
    """
    try:
        root_element = ET.fromstring(xml_str)
    except ET.ParseError as e:
        logger.error("[xml_compressor] XML 解析失败: %s", e)
        return None

    def _element_to_dict(element: ET.Element) -> Dict[str, Any]:
        """递归将 ElementTree 元素转换为节点字典。

        Args:
            element: ElementTree 元素对象

        Returns:
            包含 tag, attrs, children 的节点字典
        """
        # 将 Element 的 attrib 转换为普通字典
        attrs: Dict[str, str] = dict(element.attrib)

        # 递归处理子元素
        children: List[Dict[str, Any]] = []
        for child in element:
            children.append(_element_to_dict(child))

        return {
            'tag': element.tag,
            'attrs': attrs,
            'children': children,
        }

    return _element_to_dict(root_element)


def compress_xml(
    xml_str: str,
    max_depth: int = 8,
    max_children: int = 20,
) -> str:
    """压缩 Appium 无障碍树 XML。

    通过深度截断、属性过滤和冗余容器移除等策略，
    将原始的 XML 格式 UI 树压缩为精简的 JSON 格式。
    目标：50KB XML → 2KB JSON（95%+ 压缩率）。

    Args:
        xml_str: 原始 Appium 无障碍树 XML 字符串
        max_depth: 最大保留深度，超过此深度的节点将被截断，默认 8
        max_children: 每个节点最大保留子节点数，默认 20

    Returns:
        压缩后的 JSON 字符串
    """
    # 使用 ElementTree 解析 XML
    tree = _parse_xml_to_tree(xml_str)
    if tree is None:
        return json.dumps({'error': '无法解析 XML', 'compressed_tree': {}}, ensure_ascii=False)

    # 压缩节点树
    compressed = _node_to_dict(tree, 0, max_depth, max_children)

    # 计算压缩率统计
    original_size = len(xml_str.encode('utf-8'))
    compressed_str = json.dumps(compressed, ensure_ascii=False)
    compressed_size = len(compressed_str.encode('utf-8'))
    compression_ratio = compressed_size / original_size if original_size > 0 else 1.0

    # 统计原始和压缩后的元素数量
    def _count_elements(node: Dict[str, Any]) -> int:
        count = 1
        for child in node.get('children', []):
            count += _count_elements(child)
        return count

    original_element_count = _count_elements(tree) if tree else 0
    compressed_element_count = _count_elements(compressed) if compressed else 0

    # 包装结果
    result = {
        'compressed_tree': compressed or {},
        'element_count': {
            'original': original_element_count,
            'compressed': compressed_element_count,
        },
        'compression_ratio': round(compression_ratio, 4),
        'size': {
            'original_bytes': original_size,
            'compressed_bytes': compressed_size,
        },
    }

    return json.dumps(result, ensure_ascii=False)
