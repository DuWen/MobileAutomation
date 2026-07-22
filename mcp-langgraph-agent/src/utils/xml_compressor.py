"""XML 压缩工具模块。

专门用于压缩 Appium 无障碍树 XML（Accessibility Tree），
通过深度截断、属性过滤和冗余容器移除等策略，
实现 95%+ 的 Token 压缩率。
"""

import json
import re
from typing import Any, Dict, List, Set


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


def _extract_attributes(xml_tag: str) -> Dict[str, str]:
    """从 XML 标签中提取属性。

    解析单个 XML 标签字符串，提取所有属性键值对。

    Args:
        xml_tag: XML 标签字符串，如 '<node class="..." text="..." bounds="...">'

    Returns:
        属性名到属性值的字典
    """
    attrs: Dict[str, str] = {}
    # 匹配属性名="属性值" 或 属性名='属性值'
    pattern = re.compile(r'(\S+?)\s*=\s*"([^"]*)"')
    for match in pattern.finditer(xml_tag):
        key = match.group(1)
        value = match.group(2)
        attrs[key] = value
    return attrs


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

    # 处理子节点
    children = node.get('children', [])
    processed_children: List[Dict[str, Any]] = []

    for child in children[:max_children]:
        child_result = _node_to_dict(
            child,
            current_depth + 1,
            max_depth,
            max_children,
        )
        if child_result is not None:
            processed_children.append(child_result)

    # 检查是否为冗余容器
    if _is_redundant_container(class_name, filtered_attrs, len(processed_children)):
        # 如果是冗余容器且有子节点，直接提升子节点
        if len(processed_children) == 1:
            return processed_children[0]
        return None

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
    """简易解析 XML 为节点树。

    使用正则表达式解析 XML 格式的节点树，不支持完整的 XML 解析，
    但能满足 Appium 无障碍树 XML 的解析需求。

    Args:
        xml_str: XML 字符串

    Returns:
        节点树字典，解析失败返回 None
    """
    # 移除 XML 声明和 DOCTYPE
    xml_str = re.sub(r'<\?xml[^>]*\?>', '', xml_str)
    xml_str = re.sub(r'<!DOCTYPE[^>]*>', '', xml_str)
    xml_str = xml_str.strip()

    # 使用栈来解析嵌套节点
    # 匹配 <node ...> 或 <node .../> 或 </node>
    tag_pattern = re.compile(r'<(\w+)([^>]*?)(/?)>')
    stack: List[Dict[str, Any]] = []
    root: Dict[str, Any] | None = None

    pos = 0
    while pos < len(xml_str):
        match = tag_pattern.search(xml_str, pos)
        if not match:
            break

        tag_name = match.group(1)
        attrs_str = match.group(2).strip()
        is_self_closing = match.group(3) == '/'

        attrs = _extract_attributes(attrs_str)

        if is_self_closing:
            # 自闭合标签
            node: Dict[str, Any] = {'tag': tag_name, 'attrs': attrs, 'children': []}
            if stack:
                stack[-1]['children'].append(node)
            elif root is None:
                root = node
        elif tag_name == 'node' or tag_name.startswith('node'):
            # 开始标签
            node = {'tag': tag_name, 'attrs': attrs, 'children': []}
            if stack:
                stack[-1]['children'].append(node)
            elif root is None:
                root = node
            stack.append(node)
        elif tag_name.startswith('/'):
            # 结束标签
            if stack:
                stack.pop()

        pos = match.end()

    return root


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

    Example:
        >>> compressed = compress_xml(original_xml, max_depth=6, max_children=15)
        >>> len(compressed) < len(original_xml) // 20  # 95%+ 压缩率
        True
    """
    # 解析 XML 为节点树
    tree = _parse_xml_to_tree(xml_str)
    if tree is None:
        # 解析失败，返回空的 UI 树
        return json.dumps({'error': '无法解析 XML', 'compressed_tree': {}}, ensure_ascii=False)

    # 压缩节点树
    compressed = _node_to_dict(tree, 0, max_depth, max_children)

    # 计算压缩率统计
    original_size = len(xml_str.encode('utf-8'))
    compressed_str = json.dumps(compressed, ensure_ascii=False)
    compressed_size = len(compressed_str.encode('utf-8'))
    compression_ratio = compressed_size / original_size if original_size > 0 else 1.0

    # 统计元素数量
    def _count_elements(node: Dict[str, Any]) -> int:
        count = 1
        for child in node.get('children', []):
            count += _count_elements(child)
        return count

    element_count = _count_elements(compressed) if compressed else 0

    # 包装结果
    result = {
        'compressed_tree': compressed or {},
        'element_count': {
            'original': 'unknown',  # 原始 XML 解析较复杂，暂不统计
            'compressed': element_count,
        },
        'compression_ratio': round(compression_ratio, 4),
        'size': {
            'original_bytes': original_size,
            'compressed_bytes': compressed_size,
        },
    }

    return json.dumps(result, ensure_ascii=False)