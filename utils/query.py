"""
微信小程序信息查询模块

通过 API 查询小程序的元数据信息。
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict

import requests
from fake_useragent import UserAgent


# 缓存文件路径
CACHE_PATH = "wxid.json"

# 缓存
_cached_wxid: Dict[str, 'WxidInfo'] = {}


@dataclass
class WxidInfo:
    """小程序信息"""
    wxid: str = ""
    location: str = ""
    error: str = ""
    nickname: str = ""
    username: str = ""
    description: str = ""
    avatar: str = ""
    uses_count: str = ""
    principal_name: str = ""
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        data = {
            'nickname': self.nickname,
            'username': self.username,
            'description': self.description,
            'avatar': self.avatar,
            'uses_count': self.uses_count,
            'principal_name': self.principal_name,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)


def _load_cache() -> None:
    """加载缓存"""
    global _cached_wxid
    try:
        cache_path = Path(CACHE_PATH)
        if cache_path.exists():
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for wxid, info in data.items():
                    _cached_wxid[wxid] = WxidInfo(
                        nickname=info.get('nickname', ''),
                        username=info.get('username', ''),
                        description=info.get('description', ''),
                        avatar=info.get('avatar', ''),
                        uses_count=info.get('uses_count', ''),
                        principal_name=info.get('principal_name', ''),
                    )
    except Exception:
        pass


def _save_cache() -> None:
    """保存缓存"""
    try:
        cache_data = {}
        for wxid, info in _cached_wxid.items():
            cache_data[wxid] = {
                'nickname': info.nickname,
                'username': info.username,
                'description': info.description,
                'avatar': info.avatar,
                'uses_count': info.uses_count,
                'principal_name': info.principal_name,
            }
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def query_wxid(wxid: str) -> WxidInfo:
    """
    查询小程序信息
    
    Args:
        wxid: 小程序的 wxid
        
    Returns:
        小程序信息
    """
    global _cached_wxid
    
    # 首次调用时加载缓存
    if not _cached_wxid:
        _load_cache()
    
    # 检查缓存
    if wxid in _cached_wxid:
        info = _cached_wxid[wxid]
        info.wxid = wxid
        return info
    
    # 查询 API
    try:
        ua = UserAgent()
        headers = {
            'User-Agent': ua.random,
            'Content-Type': 'application/json;charset=utf-8',
        }
        
        resp = requests.post(
            'https://kainy.cn/api/weapp/info/',
            json={'appid': wxid},
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        
        data = resp.json()
        
        if data.get('code') != 0:
            return WxidInfo(wxid=wxid, error=data.get('errors', '查询失败'))
        
        info_data = data.get('data', {})
        info = WxidInfo(
            wxid=wxid,
            nickname=info_data.get('nickname', ''),
            username=info_data.get('username', ''),
            description=info_data.get('description', ''),
            avatar=info_data.get('avatar', ''),
            uses_count=info_data.get('uses_count', ''),
            principal_name=info_data.get('principal_name', ''),
        )
        
        # 缓存结果
        _cached_wxid[wxid] = info
        _save_cache()
        
        return info
        
    except Exception as e:
        return WxidInfo(wxid=wxid, error=str(e))


# 初始化时加载缓存
_load_cache()
