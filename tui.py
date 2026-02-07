"""
wxapkg 终端交互界面模块

使用 Textual 构建终端 UI，支持小程序列表选择。
"""

from dataclasses import dataclass
from typing import List, Optional, Callable

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich import box

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static
from textual.binding import Binding

from .utils.query import WxidInfo


class WxidTable(Static):
    """小程序信息表格组件"""
    
    def __init__(self, wxid_infos: List[WxidInfo], **kwargs):
        super().__init__(**kwargs)
        self.wxid_infos = wxid_infos
        self.selected_index = 0
    
    def compose(self) -> ComposeResult:
        yield DataTable()
    
    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("名称", "开发者", "描述")
        table.cursor_type = "row"
        
        for info in self.wxid_infos:
            table.add_row(
                info.nickname or info.wxid,
                info.principal_name or "-",
                (info.description[:40] + "...") if len(info.description) > 40 else info.description or "-"
            )


class DetailPanel(Static):
    """详情面板组件"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_info: Optional[WxidInfo] = None
    
    def update_info(self, info: WxidInfo) -> None:
        self.current_info = info
        self.refresh()
    
    def render(self) -> Text:
        if not self.current_info:
            return Text("选择一个小程序查看详情")
        
        info = self.current_info
        text = Text()
        
        if info.error:
            text.append("❌ 错误: ", style="bold red")
            text.append(info.error + "\n", style="red")
        else:
            text.append("📱 wxid: ", style="bold magenta")
            text.append(info.wxid + "\n", style="cyan")
            
            text.append("📝 名称: ", style="bold magenta")
            text.append(info.nickname + "\n", style="cyan")
            
            text.append("👤 开发者: ", style="bold magenta")
            text.append(info.principal_name + "\n", style="cyan")
            
            text.append("📄 描述: ", style="bold magenta")
            text.append(info.description + "\n", style="cyan")
        
        text.append("📁 路径: ", style="bold magenta")
        text.append(info.location + "\n", style="cyan underline")
        
        if info.avatar and not info.error:
            text.append("🖼️ 头像: ", style="bold magenta")
            text.append(info.avatar, style="cyan underline")
        
        return text


class ScanTuiApp(App):
    """扫描小程序 TUI 应用"""
    
    CSS = """
    Screen {
        layout: vertical;
    }
    
    DataTable {
        height: 15;
        margin: 1 2;
    }
    
    DetailPanel {
        height: auto;
        margin: 1 2;
        padding: 1 2;
        border: round $primary;
    }
    
    Footer {
        background: $primary-background;
    }
    """
    
    BINDINGS = [
        Binding("enter", "select", "解包"),
        Binding("q", "quit", "退出"),
        Binding("escape", "quit", "退出"),
    ]
    
    def __init__(self, wxid_infos: List[WxidInfo], **kwargs):
        super().__init__(**kwargs)
        self.wxid_infos = wxid_infos
        self.selected: Optional[WxidInfo] = None
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield WxidTable(self.wxid_infos)
        yield DetailPanel(id="detail")
        yield Footer()
    
    def on_mount(self) -> None:
        self.title = "wxapkg 小程序扫描器"
        self.sub_title = f"共 {len(self.wxid_infos)} 个小程序"
        
        if self.wxid_infos:
            detail = self.query_one("#detail", DetailPanel)
            detail.update_info(self.wxid_infos[0])
    
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            index = event.cursor_row
            if 0 <= index < len(self.wxid_infos):
                detail = self.query_one("#detail", DetailPanel)
                detail.update_info(self.wxid_infos[index])
    
    def action_select(self) -> None:
        table = self.query_one(DataTable)
        index = table.cursor_row
        if 0 <= index < len(self.wxid_infos):
            self.selected = self.wxid_infos[index]
        self.exit()
    
    def action_quit(self) -> None:
        self.exit()


def run_scan_tui(wxid_infos: List[WxidInfo]) -> Optional[WxidInfo]:
    """
    运行扫描 TUI
    
    Args:
        wxid_infos: 小程序信息列表
        
    Returns:
        用户选择的小程序信息，或 None（如果用户取消）
    """
    app = ScanTuiApp(wxid_infos)
    app.run()
    return app.selected


def print_progress(current: int, total: int) -> None:
    """打印进度"""
    console = Console()
    console.print(f"\r[green]解包进度: {current}/{total}[/green]", end="")


def print_extension_stats(ext_stats: dict) -> None:
    """打印扩展名统计"""
    console = Console()
    
    table = Table(title="文件类型统计", box=box.ROUNDED)
    table.add_column("扩展名", style="cyan")
    table.add_column("数量", style="green", justify="right")
    
    sorted_stats = sorted(ext_stats.items(), key=lambda x: x[1], reverse=True)
    for ext, count in sorted_stats:
        table.add_row(ext or "(无扩展名)", str(count))
    
    console.print(table)
