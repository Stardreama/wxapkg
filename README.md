# wxapkg

微信小程序解包工具 (Python 版)

> **免责声明**：此工具仅限于学习和研究软件内含的设计思想和原理，用户承担因使用此工具而导致的所有法律和相关责任！

## 功能

- ✅ 解密 PC 版微信的小程序 `.wxapkg` 文件
- ✅ 解包提取小程序资源文件
- ✅ 代码美化 (JSON/JavaScript/HTML)
- ✅ 查询小程序元数据 (名称、开发者、描述等)
- ✅ 终端交互界面 (TUI)

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 交互式扫描

扫描本地小程序，选择后自动解包：

```bash
python -m wxapkg scan
```

### 手动解包

指定小程序目录进行解包：

```bash
python -m wxapkg unpack -r "D:\WeChat Files\Applet\wx1234567890abcdef" -o output
```

### 参数说明

| 参数                 | 说明           | 默认值                            |
| -------------------- | -------------- | --------------------------------- |
| `-r, --root`         | 小程序目录路径 | `~/Documents/WeChat Files/Applet` |
| `-o, --output`       | 输出目录       | `unpack`                          |
| `-n, --thread`       | 线程数         | `30`                              |
| `--disable-beautify` | 禁用代码美化   | `False`                           |

## 项目结构

```
wxapkg/
├── __init__.py       # 包初始化
├── __main__.py       # 入口点
├── cli.py            # 命令行接口
├── wxapkg.py         # 核心解密解包
├── tui.py            # 终端界面
├── utils/
│   ├── beautify.py   # 代码美化
│   └── query.py      # wxid 查询
└── requirements.txt  # 依赖
```

## 解密原理

1. **PBKDF2 密钥派生**: 使用 wxid 和固定 salt 生成 AES 密钥
2. **AES-CBC 解密**: 解密前 1024 字节
3. **XOR 异或**: 解密剩余数据

## 免责声明

此工具仅限于学习和研究软件内含的设计思想和原理，用户承担因使用此工具而导致的所有法律和相关责任！
