"""
WXSS 样式还原模块

从编译后的小程序中提取并还原 WXSS 样式文件。
支持从 page-frame.html 和 app-wxss.js 提取样式。
"""

import re
import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class WxssStyle:
    """WXSS 样式信息"""
    path: str  # 页面路径，如 "pages/index/index.wxss"
    content: str  # 样式内容
    is_global: bool = False  # 是否为全局样式 (app.wxss)


class WxssRestorer:
    """
    WXSS 样式还原器
    
    从编译后的小程序中提取样式，支持：
    1. page-frame.html 中的内联样式
    2. app-wxss.js 中的 setCssToHead 调用
    3. 各页面目录下的样式文件
    """
    
    # setCssToHead 调用模式
    # setCssToHead(["path.wxss"], [...styleArray...], deviceWidth)
    SET_CSS_PATTERN = re.compile(
        r'setCssToHead\s*\(\s*'
        r'\[\s*["\']([^"\']+)["\']\s*\]\s*,\s*'  # 页面路径
        r'\[([^\]]*(?:\[[^\]]*\][^\]]*)*)\]\s*'   # 样式数组
        r'(?:,\s*(\d+))?\s*\)',                   # 可选的设备宽度
        re.DOTALL
    )
    
    # 另一种模式: __wxAppCode__["xxx.wxss"] = setCssToHead(...)
    APP_CODE_PATTERN = re.compile(
        r'__wxAppCode__\s*\[\s*["\']([^"\']+\.wxss)["\']\s*\]\s*=\s*'
        r'setCssToHead\s*\(\s*\[([^\]]*(?:\[[^\]]*\][^\]]*)*)\]\s*'
        r'(?:,\s*(\d+))?\s*\)',
        re.DOTALL
    )
    
    # 直接的 CSS 样式块
    STYLE_TAG_PATTERN = re.compile(
        r'<style[^>]*>(.*?)</style>',
        re.DOTALL | re.IGNORECASE
    )
    
    # rpx 数组模式 [type, value]
    # type 0 = rpx值, type 1 = 普通值
    RPX_ARRAY_PATTERN = re.compile(r'\[\s*(\d+)\s*,\s*([\d.]+)\s*\]')
    
    def __init__(self, base_dir: str):
        """
        初始化还原器
        
        Args:
            base_dir: 解包后的小程序根目录
        """
        self.base_dir = Path(base_dir)
        self.styles: Dict[str, WxssStyle] = {}
    
    def restore(self) -> Dict[str, str]:
        """
        执行样式还原
        
        Returns:
            字典 {页面路径: wxss内容}
        """
        # 1. 尝试从 page-frame.html 提取
        page_frame = self.base_dir / "page-frame.html"
        if page_frame.exists():
            self._extract_from_page_frame(page_frame)
        
        # 2. 尝试从 app-wxss.js 提取
        app_wxss = self.base_dir / "app-wxss.js"
        if app_wxss.exists():
            self._extract_from_app_wxss(app_wxss)
        
        # 3. 扫描各页面目录
        self._scan_page_directories()
        
        # 4. 返回结果
        return {path: style.content for path, style in self.styles.items()}
    
    def _extract_from_page_frame(self, file_path: Path) -> None:
        """从 page-frame.html 提取样式"""
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        # 提取 <style> 标签内容
        for match in self.STYLE_TAG_PATTERN.finditer(content):
            css_content = match.group(1).strip()
            if css_content:
                # 尝试识别是哪个页面的样式
                self._add_style("app.wxss", css_content, is_global=True)
        
        # 提取 setCssToHead 调用
        self._extract_set_css_calls(content)
    
    def _extract_from_app_wxss(self, file_path: Path) -> None:
        """从 app-wxss.js 提取样式"""
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        self._extract_set_css_calls(content)
    
    def _extract_set_css_calls(self, content: str) -> None:
        """提取 setCssToHead 调用中的样式"""
        
        # 模式1: setCssToHead(["path"], [...], width)
        for match in self.SET_CSS_PATTERN.finditer(content):
            path = match.group(1)
            style_array = match.group(2)
            device_width = int(match.group(3)) if match.group(3) else 375
            
            css = self._parse_style_array(style_array, device_width)
            if css:
                self._add_style(path, css)
        
        # 模式2: __wxAppCode__["xxx.wxss"] = setCssToHead([...], width)
        for match in self.APP_CODE_PATTERN.finditer(content):
            path = match.group(1)
            style_array = match.group(2)
            device_width = int(match.group(3)) if match.group(3) else 375
            
            css = self._parse_style_array(style_array, device_width)
            if css:
                self._add_style(path, css)
    
    def _parse_style_array(self, array_str: str, device_width: int = 375) -> str:
        """
        解析样式数组为 CSS 字符串
        
        样式数组格式: ["text", [0, 20], "more text", [0, 32], ...]
        其中 [0, value] 表示 rpx 值，需要保留为 rpx 单位
        """
        result = []
        
        # 分割数组元素
        parts = self._split_array_elements(array_str)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 检查是否是 rpx 数组 [type, value]
            rpx_match = self.RPX_ARRAY_PATTERN.match(part)
            if rpx_match:
                type_val = int(rpx_match.group(1))
                num_val = float(rpx_match.group(2))
                
                if type_val == 0:
                    # rpx 值
                    result.append(f"{num_val}rpx")
                else:
                    # 普通数值
                    result.append(str(num_val))
            elif part.startswith('"') or part.startswith("'"):
                # 字符串值，去掉引号
                text = part[1:-1] if len(part) >= 2 else part
                # 处理转义字符
                text = text.replace('\\n', '\n').replace('\\t', '\t')
                text = text.replace("\\'", "'").replace('\\"', '"')
                result.append(text)
        
        return ''.join(result)
    
    def _split_array_elements(self, array_str: str) -> List[str]:
        """
        分割数组元素，正确处理嵌套数组和字符串
        """
        elements = []
        current = []
        depth = 0
        in_string = False
        string_char = None
        i = 0
        
        while i < len(array_str):
            char = array_str[i]
            
            if in_string:
                current.append(char)
                if char == '\\' and i + 1 < len(array_str):
                    # 转义字符
                    current.append(array_str[i + 1])
                    i += 2
                    continue
                elif char == string_char:
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
                    # 顶层逗号，分割元素
                    elem = ''.join(current).strip()
                    if elem:
                        elements.append(elem)
                    current = []
                else:
                    current.append(char)
            
            i += 1
        
        # 添加最后一个元素
        elem = ''.join(current).strip()
        if elem:
            elements.append(elem)
        
        return elements
    
    def _scan_page_directories(self) -> None:
        """扫描页面目录中的样式文件"""
        
        # 查找 .wxss 结尾的编译文件
        for wxss_file in self.base_dir.rglob("*.wxss"):
            if wxss_file.is_file():
                try:
                    content = wxss_file.read_text(encoding='utf-8', errors='ignore')
                    rel_path = str(wxss_file.relative_to(self.base_dir))
                    rel_path = rel_path.replace('\\', '/')
                    
                    # 如果内容包含 setCssToHead，需要解析
                    if 'setCssToHead' in content:
                        self._extract_set_css_calls(content)
                    else:
                        # 直接的 CSS 内容
                        self._add_style(rel_path, content)
                except Exception:
                    pass
    
    def _add_style(self, path: str, content: str, is_global: bool = False) -> None:
        """添加样式到结果集"""
        # 规范化路径
        path = path.replace('\\', '/')
        if not path.endswith('.wxss'):
            path = path + '.wxss'
        
        # 格式化 CSS
        content = self._format_css(content)
        
        if path in self.styles:
            # 合并样式
            self.styles[path].content += '\n' + content
        else:
            self.styles[path] = WxssStyle(
                path=path,
                content=content,
                is_global=is_global
            )
    
    def _format_css(self, css: str) -> str:
        """格式化 CSS 代码"""
        # 基础清理
        css = css.strip()
        
        # 简单的格式化：每个规则独立一行
        css = re.sub(r'\s*{\s*', ' {\n  ', css)
        css = re.sub(r'\s*}\s*', '\n}\n', css)
        css = re.sub(r';\s*', ';\n  ', css)
        css = re.sub(r'\n\s*\n', '\n', css)
        
        return css.strip()
    
    def save(self, output_dir: str) -> int:
        """
        保存还原的样式文件
        
        Args:
            output_dir: 输出目录
            
        Returns:
            保存的文件数量
        """
        output_path = Path(output_dir)
        count = 0
        
        for path, style in self.styles.items():
            file_path = output_path / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(style.content, encoding='utf-8')
            count += 1
        
        return count


def restore_wxss(input_dir: str, output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    还原 WXSS 样式
    
    Args:
        input_dir: 解包后的小程序目录
        output_dir: 可选，输出目录。如果指定则保存文件
        
    Returns:
        字典 {页面路径: wxss内容}
    """
    restorer = WxssRestorer(input_dir)
    styles = restorer.restore()
    
    if output_dir:
        restorer.save(output_dir)
    
    return styles
