"""
代码美化工具模块

支持 JSON、JavaScript、HTML 文件的格式化美化。
"""

import re
import json
from typing import Optional


def pretty_json(data: bytes) -> bytes:
    """
    美化 JSON 数据
    
    Args:
        data: 原始 JSON 数据
        
    Returns:
        格式化后的 JSON 数据
    """
    try:
        obj = json.loads(data.decode('utf-8'))
        return json.dumps(obj, indent=2, ensure_ascii=False).encode('utf-8')
    except Exception:
        return data


def pretty_js(data: bytes) -> bytes:
    """
    美化 JavaScript 代码
    
    Args:
        data: 原始 JS 代码
        
    Returns:
        格式化后的 JS 代码
    """
    try:
        import jsbeautifier
        code = data.decode('utf-8').strip()
        opts = jsbeautifier.default_options()
        opts.indent_size = 2
        beautified = jsbeautifier.beautify(code, opts)
        return beautified.encode('utf-8')
    except Exception:
        return data


def pretty_html(data: bytes) -> bytes:
    """
    美化 HTML 代码，包括其中的 <script> 标签
    
    Args:
        data: 原始 HTML 代码
        
    Returns:
        格式化后的 HTML 代码
    """
    try:
        from bs4 import BeautifulSoup
        
        html = data.decode('utf-8').strip()
        soup = BeautifulSoup(html, 'lxml')
        
        # 美化 script 标签中的 JS 代码
        for script in soup.find_all('script'):
            if script.string:
                try:
                    import jsbeautifier
                    opts = jsbeautifier.default_options()
                    opts.indent_size = 2
                    beautified_js = jsbeautifier.beautify(script.string.strip(), opts)
                    script.string.replace_with('\n' + beautified_js + '\n')
                except Exception:
                    pass
        
        # 格式化 HTML
        result = soup.prettify()
        return result.encode('utf-8')
    except Exception:
        return data


# 扩展名到美化函数的映射
BEAUTIFY_MAP = {
    '.json': pretty_json,
    '.js': pretty_js,
    '.html': pretty_html,
}


def get_beautify_funcs():
    """获取美化函数映射"""
    return BEAUTIFY_MAP.copy()
