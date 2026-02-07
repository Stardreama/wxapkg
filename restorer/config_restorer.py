"""
配置文件还原模块

从编译后的小程序中提取并还原配置文件:
- app.json: 全局配置
- 页面级 .json: 页面配置
- project.config.json: 项目配置

小程序编译后，配置信息存储在 app-config.json 中。
"""

import re
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class PageConfig:
    """页面配置"""
    navigationBarTitleText: str = ""
    navigationBarBackgroundColor: str = ""
    navigationBarTextStyle: str = ""
    backgroundColor: str = ""
    backgroundTextStyle: str = ""
    enablePullDownRefresh: bool = False
    usingComponents: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，移除空值"""
        result = {}
        for key, value in asdict(self).items():
            if value and value != "" and value != {} and value != []:
                result[key] = value
        return result


@dataclass
class TabBarItem:
    """TabBar 项"""
    pagePath: str
    text: str
    iconPath: str = ""
    selectedIconPath: str = ""


@dataclass
class TabBar:
    """TabBar 配置"""
    color: str = ""
    selectedColor: str = ""
    backgroundColor: str = ""
    borderStyle: str = ""
    position: str = ""
    list: List[TabBarItem] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.color:
            result['color'] = self.color
        if self.selectedColor:
            result['selectedColor'] = self.selectedColor
        if self.backgroundColor:
            result['backgroundColor'] = self.backgroundColor
        if self.borderStyle:
            result['borderStyle'] = self.borderStyle
        if self.position:
            result['position'] = self.position
        if self.list:
            result['list'] = [asdict(item) for item in self.list]
        return result


@dataclass
class AppConfig:
    """app.json 配置"""
    pages: List[str] = field(default_factory=list)
    window: Dict[str, Any] = field(default_factory=dict)
    tabBar: Optional[TabBar] = None
    subpackages: List[Dict[str, Any]] = field(default_factory=list)
    plugins: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.pages:
            result['pages'] = self.pages
        if self.window:
            result['window'] = self.window
        if self.tabBar:
            result['tabBar'] = self.tabBar.to_dict()
        if self.subpackages:
            result['subpackages'] = self.subpackages
        if self.plugins:
            result['plugins'] = self.plugins
        return result


class ConfigRestorer:
    """
    配置文件还原器
    
    从 app-config.json 或 __wxAppCode__ 中提取配置信息
    """
    
    # __wxAppCode__ 配置模式
    APP_CODE_CONFIG_PATTERN = re.compile(
        r'__wxAppCode__\s*\[\s*["\']([^"\']+\.json)["\']\s*\]\s*=\s*(\{[^}]+\})',
        re.MULTILINE
    )
    
    def __init__(self, base_dir: str):
        """
        初始化还原器
        
        Args:
            base_dir: 解包后的小程序根目录
        """
        self.base_dir = Path(base_dir)
        self.app_config: Optional[AppConfig] = None
        self.page_configs: Dict[str, PageConfig] = {}
        self.raw_config: Dict[str, Any] = {}
    
    def restore(self) -> Dict[str, Any]:
        """
        执行配置还原
        
        Returns:
            字典 {配置文件路径: 配置内容}
        """
        # 1. 尝试读取 app-config.json
        app_config_file = self.base_dir / "app-config.json"
        if app_config_file.exists():
            self._parse_app_config(app_config_file)
        
        # 2. 从 app-service.js 提取配置
        app_service = self.base_dir / "app-service.js"
        if app_service.exists():
            self._extract_from_app_service(app_service)
        
        # 3. 扫描现有的 JSON 配置文件
        self._scan_json_files()
        
        # 4. 构建结果
        return self._build_result()
    
    def _parse_app_config(self, file_path: Path) -> None:
        """解析 app-config.json"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            config = json.loads(content)
            self.raw_config = config
            
            # 提取 pages
            pages = config.get('pages', [])
            
            # 提取 window 配置
            window = config.get('window', {})
            
            # 提取 tabBar
            tab_bar = None
            if 'tabBar' in config:
                tb = config['tabBar']
                tab_bar = TabBar(
                    color=tb.get('color', ''),
                    selectedColor=tb.get('selectedColor', ''),
                    backgroundColor=tb.get('backgroundColor', ''),
                    borderStyle=tb.get('borderStyle', ''),
                    position=tb.get('position', ''),
                    list=[TabBarItem(**item) for item in tb.get('list', [])]
                )
            
            # 提取 subpackages
            subpackages = config.get('subPackages', config.get('subpackages', []))
            
            self.app_config = AppConfig(
                pages=pages,
                window=window,
                tabBar=tab_bar,
                subpackages=subpackages,
                plugins=config.get('plugins', {})
            )
            
            # 提取页面配置
            page_configs = config.get('page', {})
            for page_path, page_config in page_configs.items():
                self.page_configs[page_path] = PageConfig(
                    navigationBarTitleText=page_config.get('navigationBarTitleText', ''),
                    navigationBarBackgroundColor=page_config.get('navigationBarBackgroundColor', ''),
                    navigationBarTextStyle=page_config.get('navigationBarTextStyle', ''),
                    backgroundColor=page_config.get('backgroundColor', ''),
                    backgroundTextStyle=page_config.get('backgroundTextStyle', ''),
                    enablePullDownRefresh=page_config.get('enablePullDownRefresh', False),
                    usingComponents=page_config.get('usingComponents', {})
                )
                
        except Exception as e:
            print(f"解析 app-config.json 失败: {e}")
    
    def _extract_from_app_service(self, file_path: Path) -> None:
        """从 app-service.js 提取配置"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            
            # 查找 __wxAppCode__ 中的 JSON 配置
            for match in self.APP_CODE_CONFIG_PATTERN.finditer(content):
                json_path = match.group(1)
                json_content = match.group(2)
                
                try:
                    config = json.loads(json_content)
                    
                    if json_path == 'app.json':
                        if not self.app_config:
                            self.app_config = AppConfig(
                                pages=config.get('pages', []),
                                window=config.get('window', {})
                            )
                    else:
                        # 页面配置
                        page_path = json_path.replace('.json', '')
                        if page_path not in self.page_configs:
                            self.page_configs[page_path] = PageConfig(
                                usingComponents=config.get('usingComponents', {})
                            )
                except json.JSONDecodeError:
                    pass
                    
        except Exception as e:
            print(f"从 app-service.js 提取配置失败: {e}")
    
    def _scan_json_files(self) -> None:
        """扫描现有的 JSON 配置文件"""
        for json_file in self.base_dir.rglob("*.json"):
            if json_file.name in ('app-config.json', 'project.config.json', 'sitemap.json'):
                continue
            
            try:
                rel_path = str(json_file.relative_to(self.base_dir))
                rel_path = rel_path.replace('\\', '/')
                
                content = json_file.read_text(encoding='utf-8', errors='ignore')
                config = json.loads(content)
                
                # 检查是否是页面配置
                if 'usingComponents' in config or 'navigationBarTitleText' in config:
                    page_path = rel_path.replace('.json', '')
                    if page_path not in self.page_configs:
                        self.page_configs[page_path] = PageConfig(
                            navigationBarTitleText=config.get('navigationBarTitleText', ''),
                            usingComponents=config.get('usingComponents', {})
                        )
                        
            except Exception:
                pass
    
    def _build_result(self) -> Dict[str, str]:
        """构建结果字典"""
        result = {}
        
        # app.json
        if self.app_config:
            result['app.json'] = json.dumps(
                self.app_config.to_dict(),
                indent=2,
                ensure_ascii=False
            )
        
        # 页面配置
        for page_path, config in self.page_configs.items():
            config_dict = config.to_dict()
            if config_dict:  # 只有非空配置才输出
                json_path = f"{page_path}.json"
                result[json_path] = json.dumps(
                    config_dict,
                    indent=2,
                    ensure_ascii=False
                )
        
        # project.config.json (基础模板)
        if self.app_config and self.app_config.pages:
            # 尝试从 wxid 推断 appid
            appid = ""
            for part in str(self.base_dir).split(os.sep):
                if part.startswith('wx') and len(part) == 18:
                    appid = part
                    break
            
            project_config = {
                "description": "项目配置文件",
                "packOptions": {
                    "ignore": []
                },
                "setting": {
                    "urlCheck": True,
                    "es6": True,
                    "postcss": True,
                    "minified": True
                },
                "compileType": "miniprogram",
                "appid": appid,
                "projectname": appid or "miniprogram"
            }
            result['project.config.json'] = json.dumps(
                project_config,
                indent=2,
                ensure_ascii=False
            )
        
        return result
    
    def save(self, output_dir: str) -> int:
        """
        保存还原的配置文件
        
        Args:
            output_dir: 输出目录
            
        Returns:
            保存的文件数量
        """
        output_path = Path(output_dir)
        configs = self._build_result()
        count = 0
        
        for path, content in configs.items():
            file_path = output_path / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding='utf-8')
            count += 1
        
        return count


def restore_config(input_dir: str, output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    还原配置文件
    
    Args:
        input_dir: 解包后的小程序目录
        output_dir: 可选，输出目录
        
    Returns:
        字典 {配置路径: 配置内容}
    """
    restorer = ConfigRestorer(input_dir)
    configs = restorer.restore()
    
    if output_dir:
        restorer.save(output_dir)
    
    return configs
