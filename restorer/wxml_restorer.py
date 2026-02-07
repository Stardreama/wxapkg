"""
WXML 模板还原模块

从编译后的小程序中提取并还原 WXML 模板文件。
WXML 被编译为 z 数组指令集，通过 $gwx 函数渲染。

编译格式示例:
var z = [];
z.push(['view',['class','container'],'text content']);

本模块将 z 数组指令反向解析为 WXML 标签结构。
"""

import re
import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from html import escape as html_escape


@dataclass
class WxmlNode:
    """WXML 节点"""
    tag: str
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List[Union['WxmlNode', str]] = field(default_factory=list)
    is_text: bool = False
    
    def to_wxml(self, indent: int = 0) -> str:
        """转换为 WXML 字符串"""
        prefix = '  ' * indent
        
        if self.is_text:
            return f"{prefix}{self.tag}\n" if self.tag.strip() else ""
        
        # 自闭合标签
        self_closing = ['image', 'input', 'import', 'include', 'wxs']
        
        # 构建属性字符串
        attrs_str = ''
        for key, value in self.attrs.items():
            if value is True:
                attrs_str += f' {key}'
            elif value is not None:
                # 处理数据绑定
                attrs_str += f' {key}="{value}"'
        
        if not self.children and self.tag in self_closing:
            return f'{prefix}<{self.tag}{attrs_str} />\n'
        
        if not self.children:
            return f'{prefix}<{self.tag}{attrs_str}></{self.tag}>\n'
        
        # 检查是否只有文本子节点
        if len(self.children) == 1 and isinstance(self.children[0], str):
            text = self.children[0].strip()
            if '\n' not in text and len(text) < 60:
                return f'{prefix}<{self.tag}{attrs_str}>{text}</{self.tag}>\n'
        
        # 多行输出
        result = f'{prefix}<{self.tag}{attrs_str}>\n'
        for child in self.children:
            if isinstance(child, WxmlNode):
                result += child.to_wxml(indent + 1)
            elif isinstance(child, str) and child.strip():
                result += f'{"  " * (indent + 1)}{child.strip()}\n'
        result += f'{prefix}</{self.tag}>\n'
        
        return result


class WxmlRestorer:
    """
    WXML 模板还原器
    
    支持从以下来源还原:
    1. app-service.js 中的编译模板
    2. 各页面目录下的 .wxml 编译文件
    3. page-frame.html 中的模板定义
    """
    
    # $gwx 函数调用模式
    GWX_PATTERN = re.compile(
        r'\$gwx\s*\(\s*["\']([^"\']+\.wxml)["\']\s*\)',
        re.MULTILINE
    )
    
    # z 数组定义模式
    Z_ARRAY_PATTERN = re.compile(
        r'var\s+z\s*=\s*\[\s*\]',
        re.MULTILINE
    )
    
    # z.push 调用模式 - 匹配数组内容
    Z_PUSH_PATTERN = re.compile(
        r'z\.push\s*\(\s*(\[[\s\S]*?\])\s*\)',
        re.MULTILINE
    )
    
    # __wxAppCode__ WXML 定义
    APP_CODE_WXML_PATTERN = re.compile(
        r'__wxAppCode__\s*\[\s*["\']([^"\']+\.wxml)["\']\s*\]\s*=\s*\$gwx\s*\(',
        re.MULTILINE
    )
    
    # 函数定义模式 (包含 WXML 渲染代码)
    FUNC_PATTERN = re.compile(
        r'function\s*\(\s*\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
        re.MULTILINE | re.DOTALL
    )
    
    # WXML 注释中的路径信息
    WXML_PATH_COMMENT = re.compile(
        r'/\*\s*([^\*]+\.wxml)\s*\*/',
        re.MULTILINE
    )
    
    def __init__(self, base_dir: str):
        """
        初始化还原器
        
        Args:
            base_dir: 解包后的小程序根目录
        """
        self.base_dir = Path(base_dir)
        self.templates: Dict[str, str] = {}
        self.debug = False
    
    def restore(self) -> Dict[str, str]:
        """
        执行 WXML 还原
        
        Returns:
            字典 {页面路径: wxml内容}
        """
        # 1. 扫描现有的 .wxml 文件
        self._scan_wxml_files()
        
        # 2. 从 app-service.js 提取
        app_service = self.base_dir / "app-service.js"
        if app_service.exists():
            self._extract_from_app_service(app_service)
        
        # 3. 从 page-frame.html 提取
        page_frame = self.base_dir / "page-frame.html"
        if page_frame.exists():
            self._extract_from_page_frame(page_frame)
        
        # 4. 扫描各页面目录
        self._scan_page_directories()
        
        return self.templates
    
    def _scan_wxml_files(self) -> None:
        """扫描已存在的 .wxml 文件"""
        for wxml_file in self.base_dir.rglob("*.wxml"):
            if wxml_file.is_file():
                try:
                    content = wxml_file.read_text(encoding='utf-8', errors='ignore')
                    rel_path = str(wxml_file.relative_to(self.base_dir))
                    rel_path = rel_path.replace('\\', '/')
                    
                    # 检查是否是编译后的内容还是原始 WXML
                    if self._is_compiled_wxml(content):
                        # 需要还原
                        restored = self._restore_from_compiled(content, rel_path)
                        if restored:
                            self.templates[rel_path] = restored
                    else:
                        # 已经是原始 WXML
                        self.templates[rel_path] = content
                except Exception as e:
                    if self.debug:
                        print(f"读取 {wxml_file} 失败: {e}")
    
    def _is_compiled_wxml(self, content: str) -> bool:
        """判断是否是编译后的 WXML"""
        # 编译后的特征: 包含 JS 代码而非 XML 标签
        if content.strip().startswith('<'):
            return False
        if 'var z=' in content or 'z.push' in content:
            return True
        if '$gwx' in content:
            return True
        return False
    
    def _extract_from_app_service(self, file_path: Path) -> None:
        """从 app-service.js 提取 WXML 模板"""
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        # 查找所有 WXML 路径引用
        for match in self.APP_CODE_WXML_PATTERN.finditer(content):
            wxml_path = match.group(1)
            if wxml_path not in self.templates:
                # 尝试提取对应的模板代码
                template = self._extract_template_block(content, wxml_path)
                if template:
                    self.templates[wxml_path] = template
    
    def _extract_from_page_frame(self, file_path: Path) -> None:
        """从 page-frame.html 提取 WXML 模板定义"""
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        # 查找 $gwx 调用
        for match in self.GWX_PATTERN.finditer(content):
            wxml_path = match.group(1)
            if wxml_path not in self.templates:
                template = self._extract_template_block(content, wxml_path)
                if template:
                    self.templates[wxml_path] = template
    
    def _scan_page_directories(self) -> None:
        """扫描页面目录中的编译 WXML"""
        # 查找所有包含编译 WXML 的 JS 文件
        for js_file in self.base_dir.rglob("*.js"):
            if js_file.name in ('app-service.js', 'app-wxss.js'):
                continue
            
            try:
                content = js_file.read_text(encoding='utf-8', errors='ignore')
                
                # 检查是否包含 WXML 相关代码
                if 'z.push' in content or '$gwx' in content:
                    # 推断 WXML 路径
                    wxml_path = str(js_file.relative_to(self.base_dir))
                    wxml_path = wxml_path.replace('\\', '/').replace('.js', '.wxml')
                    
                    if wxml_path not in self.templates:
                        template = self._restore_from_compiled(content, wxml_path)
                        if template:
                            self.templates[wxml_path] = template
            except Exception:
                pass
    
    def _extract_template_block(self, content: str, wxml_path: str) -> Optional[str]:
        """从代码中提取指定路径的模板块"""
        # 构建搜索模式
        escaped_path = re.escape(wxml_path)
        
        # 尝试多种模式
        patterns = [
            # 模式1: __wxAppCode__["path.wxml"] = $gwx(...)
            rf'__wxAppCode__\s*\[\s*["\']' + escaped_path + r'["\']\s*\]\s*=\s*\$gwx\s*\([^)]*\)\s*;?\s*(function\s*\([^)]*\)\s*\{{[\s\S]*?\}})',
            # 模式2: 在路径注释后的函数
            rf'/\*\s*' + escaped_path + r'\s*\*/\s*(function\s*\([^)]*\)\s*\{{[\s\S]*?\}})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                func_content = match.group(1)
                return self._restore_from_compiled(func_content, wxml_path)
        
        return None
    
    def _restore_from_compiled(self, content: str, path: str = "") -> Optional[str]:
        """
        从编译后的代码还原 WXML
        
        解析 z.push 调用并重建 WXML 结构
        """
        nodes = []
        
        # 提取所有 z.push 调用
        for match in self.Z_PUSH_PATTERN.finditer(content):
            try:
                array_str = match.group(1)
                node = self._parse_z_array(array_str)
                if node:
                    nodes.append(node)
            except Exception as e:
                if self.debug:
                    print(f"解析 z.push 失败: {e}")
        
        if not nodes:
            # 尝试其他解析方式
            return self._try_alternative_restore(content, path)
        
        # 构建 WXML
        result = ""
        for node in nodes:
            if isinstance(node, WxmlNode):
                result += node.to_wxml()
            elif isinstance(node, str):
                result += node + "\n"
        
        return result.strip() if result.strip() else None
    
    def _parse_z_array(self, array_str: str) -> Optional[WxmlNode]:
        """
        解析 z.push 的数组参数
        
        格式: [tagName, [attrName, attrValue, ...], [children...]]
        或: [tagName, [attrs], textContent]
        """
        try:
            # 清理并解析
            array_str = array_str.strip()
            
            # 使用简单的解析方法
            parts = self._split_array_safe(array_str)
            
            if not parts:
                return None
            
            tag = parts[0].strip().strip('"\'')
            
            if not tag or tag.isdigit():
                return None
            
            node = WxmlNode(tag=tag)
            
            # 解析属性
            if len(parts) > 1:
                attrs_part = parts[1]
                if isinstance(attrs_part, list):
                    node.attrs = self._parse_attrs(attrs_part)
                elif isinstance(attrs_part, str) and attrs_part.startswith('['):
                    node.attrs = self._parse_attrs_str(attrs_part)
            
            # 解析子节点
            if len(parts) > 2:
                for child_part in parts[2:]:
                    if isinstance(child_part, str):
                        child_part = child_part.strip().strip('"\'')
                        if child_part:
                            node.children.append(child_part)
            
            return node
            
        except Exception as e:
            if self.debug:
                print(f"解析数组失败: {e}")
            return None
    
    def _split_array_safe(self, array_str: str) -> List[Any]:
        """安全地分割数组字符串"""
        if not array_str.startswith('[') or not array_str.endswith(']'):
            return []
        
        inner = array_str[1:-1].strip()
        if not inner:
            return []
        
        parts = []
        current = []
        depth = 0
        in_string = False
        string_char = None
        
        for i, char in enumerate(inner):
            if in_string:
                current.append(char)
                if char == '\\' and i + 1 < len(inner):
                    continue
                if char == string_char:
                    in_string = False
            else:
                if char in '"\'':
                    in_string = True
                    string_char = char
                    current.append(char)
                elif char == '[':
                    depth += 1
                    current.append(char)
                elif char == ']':
                    depth -= 1
                    current.append(char)
                elif char == ',' and depth == 0:
                    part = ''.join(current).strip()
                    if part:
                        parts.append(part)
                    current = []
                else:
                    current.append(char)
        
        # 最后一部分
        part = ''.join(current).strip()
        if part:
            parts.append(part)
        
        return parts
    
    def _parse_attrs(self, attrs: List) -> Dict[str, str]:
        """解析属性列表"""
        result = {}
        i = 0
        while i < len(attrs) - 1:
            key = str(attrs[i]).strip().strip('"\'')
            value = str(attrs[i + 1]).strip().strip('"\'')
            result[key] = value
            i += 2
        return result
    
    def _parse_attrs_str(self, attrs_str: str) -> Dict[str, str]:
        """解析属性字符串"""
        parts = self._split_array_safe(attrs_str)
        return self._parse_attrs(parts) if parts else {}
    
    def _try_alternative_restore(self, content: str, path: str) -> Optional[str]:
        """尝试其他还原方式"""
        # 查找可能的标签定义
        tags = []
        
        # 模式: 直接的标签字符串
        tag_pattern = re.compile(r'["\'](<[a-z][^>]*>.*?</[a-z]+>)["\']', re.DOTALL | re.IGNORECASE)
        for match in tag_pattern.finditer(content):
            tag = match.group(1)
            if self._is_valid_wxml_tag(tag):
                tags.append(tag)
        
        if tags:
            return '\n'.join(tags)
        
        return None
    
    def _is_valid_wxml_tag(self, tag: str) -> bool:
        """检查是否是有效的 WXML 标签"""
        valid_tags = [
            'view', 'text', 'image', 'button', 'input', 'scroll-view',
            'swiper', 'swiper-item', 'icon', 'navigator', 'form',
            'checkbox', 'radio', 'picker', 'slider', 'switch',
            'textarea', 'video', 'audio', 'map', 'canvas',
            'block', 'template', 'import', 'include', 'wxs'
        ]
        for t in valid_tags:
            if f'<{t}' in tag.lower():
                return True
        return False
    
    def save(self, output_dir: str) -> int:
        """
        保存还原的 WXML 文件
        
        Args:
            output_dir: 输出目录
            
        Returns:
            保存的文件数量
        """
        output_path = Path(output_dir)
        count = 0
        
        for path, content in self.templates.items():
            file_path = output_path / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding='utf-8')
            count += 1
        
        return count


def restore_wxml(input_dir: str, output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    还原 WXML 模板
    
    Args:
        input_dir: 解包后的小程序目录
        output_dir: 可选，输出目录
        
    Returns:
        字典 {页面路径: wxml内容}
    """
    restorer = WxmlRestorer(input_dir)
    templates = restorer.restore()
    
    if output_dir:
        restorer.save(output_dir)
    
    return templates
