"""
wxapkg 核心解密和解包模块

实现微信小程序 .wxapkg 文件的解密和解包功能。
解密算法: PBKDF2 密钥派生 + AES-CBC 解密 + XOR 异或
"""

import os
import struct
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import List, Callable, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

# 解密常量
SALT = b"saltiest"
IV = b"the iv: 16 bytes"
PBKDF2_ITERATIONS = 1000
PBKDF2_KEY_LENGTH = 32

# wxapkg 格式常量
FIRST_MARK = 0xBE
LAST_MARK = 0xED


@dataclass
class WxapkgFile:
    """wxapkg 包中的单个文件信息"""
    name: str
    offset: int
    size: int


def decrypt_file(wxid: str, wxapkg_path: str) -> bytes:
    """
    解密 wxapkg 文件
    
    Args:
        wxid: 小程序的 wxid (如 wx1234567890abcdef)
        wxapkg_path: wxapkg 文件路径
        
    Returns:
        解密后的数据
    """
    with open(wxapkg_path, 'rb') as f:
        data = f.read()
    
    # PBKDF2 密钥派生
    from Crypto.Hash import SHA1
    dk = PBKDF2(
        password=wxid.encode('utf-8'),
        salt=SALT,
        dkLen=PBKDF2_KEY_LENGTH,
        count=PBKDF2_ITERATIONS,
        hmac_hash_module=SHA1
    )
    
    # AES-CBC 解密前 1024 字节 (跳过前 6 字节)
    cipher = AES.new(dk, AES.MODE_CBC, IV)
    decrypted_header = cipher.decrypt(data[6:1024 + 6])
    
    # XOR 解密剩余数据
    xor_key = ord(wxid[-2]) if len(wxid) >= 2 else 0x66
    xor_data = bytes(b ^ xor_key for b in data[1024 + 6:])
    
    # 组合解密数据 (取前 1023 字节 + XOR 解密的数据)
    result = decrypted_header[:1023] + xor_data
    
    return result


def parse_wxapkg(data: bytes) -> List[WxapkgFile]:
    """
    解析 wxapkg 文件格式
    
    Args:
        data: 解密后的数据
        
    Returns:
        文件列表
        
    Raises:
        ValueError: 如果不是有效的 wxapkg 文件
    """
    offset = 0
    
    # 读取头部
    first_mark = data[offset]
    offset += 1
    
    info1 = struct.unpack('>I', data[offset:offset + 4])[0]
    offset += 4
    
    index_info_length = struct.unpack('>I', data[offset:offset + 4])[0]
    offset += 4
    
    body_info_length = struct.unpack('>I', data[offset:offset + 4])[0]
    offset += 4
    
    last_mark = data[offset]
    offset += 1
    
    # 验证标记
    if first_mark != FIRST_MARK or last_mark != LAST_MARK:
        raise ValueError("无效的 wxapkg 文件: 标记验证失败")
    
    # 读取文件数量
    file_count = struct.unpack('>I', data[offset:offset + 4])[0]
    offset += 4
    
    # 读取文件索引
    file_list: List[WxapkgFile] = []
    for _ in range(file_count):
        name_len = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4
        
        if name_len > 10 * 1024 * 1024:  # 10 MB
            raise ValueError("无效的文件名长度")
        
        name = data[offset:offset + name_len].decode('utf-8')
        offset += name_len
        
        file_offset = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4
        
        file_size = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4
        
        file_list.append(WxapkgFile(name=name, offset=file_offset, size=file_size))
    
    return file_list


def unpack(
    decrypted_data: bytes,
    output_dir: str,
    thread_count: int = 30,
    beautify: bool = True,
    beautify_funcs: Optional[Dict[str, Callable[[bytes], bytes]]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> int:
    """
    解包 wxapkg 文件
    
    Args:
        decrypted_data: 解密后的数据
        output_dir: 输出目录
        thread_count: 线程数
        beautify: 是否美化代码
        beautify_funcs: 美化函数映射 (扩展名 -> 函数)
        progress_callback: 进度回调函数 (current, total)
        
    Returns:
        解包的文件数量
    """
    file_list = parse_wxapkg(decrypted_data)
    
    if beautify_funcs is None:
        beautify_funcs = {}
    
    ext_stats: Dict[str, int] = {}
    
    def save_file(file_info: WxapkgFile) -> str:
        """保存单个文件"""
        output_path = Path(output_dir) / file_info.name.lstrip('/')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_data = decrypted_data[file_info.offset:file_info.offset + file_info.size]
        
        # 统计扩展名
        ext = output_path.suffix.lower()
        ext_stats[ext] = ext_stats.get(ext, 0) + 1
        
        # 美化代码
        if beautify and ext in beautify_funcs:
            try:
                file_data = beautify_funcs[ext](file_data)
            except Exception:
                pass  # 美化失败则使用原始数据
        
        output_path.write_bytes(file_data)
        return str(output_path)
    
    # 多线程保存文件
    completed = 0
    total = len(file_list)
    
    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = {executor.submit(save_file, f): f for f in file_list}
        
        for future in as_completed(futures):
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
            try:
                future.result()
            except Exception as e:
                print(f"保存文件失败: {e}")
    
    return len(file_list)


def decrypt_and_unpack(
    wxid: str,
    wxapkg_path: str,
    output_dir: str,
    thread_count: int = 30,
    beautify: bool = True,
    beautify_funcs: Optional[Dict[str, Callable[[bytes], bytes]]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> int:
    """
    解密并解包 wxapkg 文件
    
    Args:
        wxid: 小程序的 wxid
        wxapkg_path: wxapkg 文件路径
        output_dir: 输出目录
        thread_count: 线程数
        beautify: 是否美化代码
        beautify_funcs: 美化函数映射
        progress_callback: 进度回调
        
    Returns:
        解包的文件数量
    """
    decrypted_data = decrypt_file(wxid, wxapkg_path)
    return unpack(
        decrypted_data,
        output_dir,
        thread_count,
        beautify,
        beautify_funcs,
        progress_callback
    )


def scan_wxapkg_files(root: str) -> List[str]:
    """
    扫描目录下的所有 .wxapkg 文件
    
    Args:
        root: 根目录
        
    Returns:
        wxapkg 文件路径列表
    """
    result = []
    root_path = Path(root)
    
    if root_path.is_file() and root_path.suffix == '.wxapkg':
        return [str(root_path)]
    
    for path in root_path.rglob('*.wxapkg'):
        result.append(str(path))
    
    return result


def parse_wxid_from_path(path: str) -> Optional[str]:
    """
    从路径中解析 wxid
    
    Args:
        path: 文件或目录路径
        
    Returns:
        wxid 或 None
    """
    import re
    match = re.search(r'(wx[0-9a-f]{16})', path)
    return match.group(1) if match else None
