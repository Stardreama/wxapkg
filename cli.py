"""
wxapkg 命令行界面

提供 scan 和 unpack 两个主要命令。
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .wxapkg import (
    decrypt_and_unpack,
    scan_wxapkg_files,
    parse_wxid_from_path,
)
from .utils.query import query_wxid, WxidInfo
from .utils.beautify import get_beautify_funcs


console = Console()


def get_default_applet_path() -> str:
    """获取默认的小程序路径"""
    home = Path.home()
    return str(home / "Documents" / "WeChat Files" / "Applet")


@click.group()
@click.version_option(version="1.0.0", prog_name="wxapkg")
def cli():
    """wxapkg - 微信小程序解包工具 (Python 版)"""
    pass


@cli.command()
@click.option(
    '-r', '--root',
    default=get_default_applet_path,
    help='小程序目录路径'
)
def scan(root: str):
    """扫描并选择小程序进行解包"""
    
    if not os.path.exists(root):
        console.print(f"[red]错误: 目录不存在: {root}[/red]")
        sys.exit(1)
    
    # 扫描目录
    console.print(f"[cyan]正在扫描: {root}[/cyan]")
    
    wxid_pattern = re.compile(r'(wx[0-9a-f]{16})')
    wxid_infos = []
    
    try:
        for entry in os.scandir(root):
            if not entry.is_dir():
                continue
            
            match = wxid_pattern.search(entry.name)
            if not match:
                continue
            
            wxid = match.group(1)
            
            with console.status(f"[yellow]查询小程序信息: {wxid}[/yellow]"):
                info = query_wxid(wxid)
                info.wxid = wxid
                info.location = entry.path
                wxid_infos.append(info)
    
    except Exception as e:
        console.print(f"[red]扫描失败: {e}[/red]")
        sys.exit(1)
    
    if not wxid_infos:
        console.print("[yellow]未找到任何小程序[/yellow]")
        return
    
    console.print(f"[green]找到 {len(wxid_infos)} 个小程序[/green]")
    
    # 运行 TUI
    from .tui import run_scan_tui
    selected = run_scan_tui(wxid_infos)
    
    if not selected:
        console.print("[yellow]已取消[/yellow]")
        return
    
    # 解包选中的小程序
    console.print(f"[cyan]开始解包: {selected.nickname or selected.wxid}[/cyan]")
    
    output_dir = selected.wxid
    _do_unpack(selected.location, output_dir, selected.wxid, 30, True)
    
    # 保存详情
    detail_path = Path(output_dir) / "detail.json"
    detail_path.write_text(selected.to_json(), encoding='utf-8')
    console.print(f"[cyan]小程序详情已保存到: {detail_path}[/cyan]")


@cli.command()
@click.option(
    '-r', '--root',
    required=True,
    help='小程序目录路径 (包含 .wxapkg 文件)'
)
@click.option(
    '-o', '--output',
    default='unpack',
    help='输出目录'
)
@click.option(
    '-n', '--thread',
    default=30,
    type=int,
    help='线程数'
)
@click.option(
    '--disable-beautify',
    is_flag=True,
    default=False,
    help='禁用代码美化'
)
def unpack(root: str, output: str, thread: int, disable_beautify: bool):
    """解密并解包指定的小程序"""
    
    if not os.path.exists(root):
        console.print(f"[red]错误: 路径不存在: {root}[/red]")
        sys.exit(1)
    
    # 解析 wxid
    wxid = parse_wxid_from_path(root)
    if not wxid:
        console.print("[red]错误: 无法从路径解析 wxid[/red]")
        console.print("[yellow]路径应包含类似 wx1234567890abcdef 的 wxid[/yellow]")
        sys.exit(1)
    
    _do_unpack(root, output, wxid, thread, not disable_beautify)


def _do_unpack(root: str, output: str, wxid: str, thread: int, beautify: bool):
    """执行解包操作"""
    
    console.print(f"[cyan]wxid: {wxid}[/cyan]")
    console.print(f"[cyan]线程数: {thread}[/cyan]")
    console.print(f"[cyan]代码美化: {'是' if beautify else '否'}[/cyan]")
    
    # 扫描 wxapkg 文件
    root_path = Path(root)
    
    if root_path.is_file():
        # 单个文件
        wxapkg_files = [str(root_path)]
        sub_dirs = [root_path.stem]
    else:
        # 目录
        sub_dirs = []
        wxapkg_files_by_subdir = {}
        
        for entry in root_path.iterdir():
            if entry.is_dir():
                files = scan_wxapkg_files(str(entry))
                if files:
                    sub_dirs.append(entry.name)
                    wxapkg_files_by_subdir[entry.name] = files
    
    if root_path.is_file():
        # 单个文件处理
        beautify_funcs = get_beautify_funcs() if beautify else {}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]解包中...", total=100)
            
            def update_progress(current, total):
                progress.update(task, completed=int(current / total * 100))
            
            file_count = decrypt_and_unpack(
                wxid=wxid,
                wxapkg_path=str(root_path),
                output_dir=output,
                thread_count=thread,
                beautify=beautify,
                beautify_funcs=beautify_funcs,
                progress_callback=update_progress
            )
        
        console.print(f"[green]解包完成: {file_count} 个文件[/green]")
        console.print(f"[cyan]输出目录: {output}[/cyan]")
    else:
        # 目录处理
        total_files = 0
        beautify_funcs = get_beautify_funcs() if beautify else {}
        
        for subdir in sub_dirs:
            subdir_output = Path(output) / subdir
            files = wxapkg_files_by_subdir.get(subdir, [])
            
            for wxapkg_file in files:
                console.print(f"[yellow]解包: {Path(wxapkg_file).name}[/yellow]")
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]解包中...", total=100)
                    
                    def update_progress(current, total):
                        progress.update(task, completed=int(current / total * 100))
                    
                    file_count = decrypt_and_unpack(
                        wxid=wxid,
                        wxapkg_path=wxapkg_file,
                        output_dir=str(subdir_output),
                        thread_count=thread,
                        beautify=beautify,
                        beautify_funcs=beautify_funcs,
                        progress_callback=update_progress
                    )
                    total_files += file_count
        
        console.print(f"[green]全部解包完成: {total_files} 个文件[/green]")
        console.print(f"[cyan]输出目录: {output}[/cyan]")


@cli.command()
@click.option(
    '-i', '--input',
    required=True,
    help='解包后的小程序目录'
)
@click.option(
    '-o', '--output',
    default=None,
    help='输出目录 (默认在 input 目录下创建 restored 子目录)'
)
@click.option(
    '-t', '--type',
    type=click.Choice(['wxss', 'wxml', 'config', 'all']),
    default='all',
    help='还原类型: wxss=样式, wxml=模板, config=配置, all=全部'
)
def restore(input: str, output: Optional[str], type: str):
    """还原小程序源码 (WXML 模板、WXSS 样式、配置文件)"""
    
    if not os.path.exists(input):
        console.print(f"[red]错误: 目录不存在: {input}[/red]")
        sys.exit(1)
    
    # 默认输出目录
    if output is None:
        output = os.path.join(input, 'restored')
    
    console.print(f"[cyan]输入目录: {input}[/cyan]")
    console.print(f"[cyan]输出目录: {output}[/cyan]")
    console.print(f"[cyan]还原类型: {type}[/cyan]")
    
    # Config 还原
    if type in ('config', 'all'):
        console.print("\n[yellow]正在还原配置文件...[/yellow]")
        
        try:
            from .restorer import ConfigRestorer
            
            restorer = ConfigRestorer(input)
            configs = restorer.restore()
            
            if configs:
                count = restorer.save(output)
                console.print(f"[green]✓ 配置还原完成: {count} 个配置文件[/green]")
                
                for path in sorted(configs.keys())[:10]:
                    console.print(f"  [dim]{path}[/dim]")
                if len(configs) > 10:
                    console.print(f"  [dim]... 及其他 {len(configs) - 10} 个文件[/dim]")
            else:
                console.print("[yellow]未找到可还原的配置文件[/yellow]")
                
        except Exception as e:
            console.print(f"[red]配置还原失败: {e}[/red]")
    
    # WXML 还原
    if type in ('wxml', 'all'):
        console.print("\n[yellow]正在还原 WXML 模板...[/yellow]")
        
        try:
            from .restorer import WxmlRestorer
            
            restorer = WxmlRestorer(input)
            templates = restorer.restore()
            
            if templates:
                count = restorer.save(output)
                console.print(f"[green]✓ WXML 还原完成: {count} 个模板文件[/green]")
                
                for path in sorted(templates.keys())[:10]:
                    console.print(f"  [dim]{path}[/dim]")
                if len(templates) > 10:
                    console.print(f"  [dim]... 及其他 {len(templates) - 10} 个文件[/dim]")
            else:
                console.print("[yellow]未找到可还原的 WXML 模板[/yellow]")
                
        except Exception as e:
            console.print(f"[red]WXML 还原失败: {e}[/red]")
    
    # WXSS 还原
    if type in ('wxss', 'all'):
        console.print("\n[yellow]正在还原 WXSS 样式...[/yellow]")
        
        try:
            from .restorer import WxssRestorer
            
            restorer = WxssRestorer(input)
            styles = restorer.restore()
            
            if styles:
                count = restorer.save(output)
                console.print(f"[green]✓ WXSS 还原完成: {count} 个样式文件[/green]")
                
                for path in sorted(styles.keys())[:10]:
                    console.print(f"  [dim]{path}[/dim]")
                if len(styles) > 10:
                    console.print(f"  [dim]... 及其他 {len(styles) - 10} 个文件[/dim]")
            else:
                console.print("[yellow]未找到可还原的 WXSS 样式[/yellow]")
                
        except Exception as e:
            console.print(f"[red]WXSS 还原失败: {e}[/red]")
    
    console.print(f"\n[green]还原完成![/green]")
    console.print(f"[cyan]输出目录: {output}[/cyan]")


def main():
    """主入口"""
    cli()


if __name__ == '__main__':
    main()

