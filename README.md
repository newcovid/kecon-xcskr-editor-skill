# Kecon xRobotDesigner `.xcskr` Editor Skill

一个面向 Codex 的非官方 Skill，用于检查、摘要、导出和安全修改科聪
xRobotDesigner `.xcskr` PLC 工程。

## 功能

- 将 GBK XML 工程导出为紧凑的 AI 可读结构包。
- 检查控制方案、任务、程序、功能块、变量和用户数据类型。
- 导出 LD/FBD 的块、引脚、连接和连线结构。
- 提取或替换 ST，并尽量保留原始换行格式。
- 定点修改变量、POU、硬件标签、CAN/CANopen 对象和映射属性。
- 创建时间戳备份，并提供 ST 格式和 CANopen 命令 ID 静态检查。

## 仓库结构

```text
kecon-xcskr-editor-skill/
├── README.md
├── .gitignore
└── kecon-xcskr-editor/
    ├── SKILL.md
    ├── agents/
    ├── references/
    ├── scripts/
    └── tests/
```

## 安装

需要 Python 3.10 或更高版本，运行时只使用 Python 标准库。

```powershell
git clone https://github.com/newcovid/kecon-xcskr-editor-skill.git
$skillSource = Resolve-Path ".\kecon-xcskr-editor-skill\kecon-xcskr-editor"
$skillRoot = Join-Path $env:USERPROFILE ".codex\skills"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -Recurse -LiteralPath $skillSource -Destination $skillRoot
```

如果使用了自定义 Codex Skills 目录，请把 `kecon-xcskr-editor` 复制到相应目录。
重新启动或刷新 Codex 后，可用 `$kecon-xcskr-editor` 显式调用。

## 本地验证

在仓库根目录运行：

```powershell
python -m unittest discover -s ".\kecon-xcskr-editor\tests" -v
python ".\kecon-xcskr-editor\scripts\xcskr_tool.py" --help
```

## 直接使用脚本

导出 AI 可读结构包：

```powershell
python ".\kecon-xcskr-editor\scripts\xcskr_tool.py" export-ai `
  --project "D:\path\project.xcskr" `
  --output-dir "$env:TEMP\kecon_ai_pack" `
  --st-mode files
```

搜索随 Skill 提供的精简帮助知识库：

```powershell
python ".\kecon-xcskr-editor\scripts\kecon_help.py" search "CANopen"
```

完整命令及安全约束请参阅
[`kecon-xcskr-editor/SKILL.md`](kecon-xcskr-editor/SKILL.md)。

## 安全说明

- 工具默认在写入前创建时间戳备份；风险较高的操作请先使用 `--dry-run`。
- 不要使用 XML 序列化器重写整个 `.xcskr`，否则可能破坏 ST 的换行格式。
- 静态检查不能替代 xRobotDesigner GUI 中的编译、下载和现场验证。
- `.xcskr` 工程可能包含客户名称、设备地址、工艺参数和控制逻辑；本仓库默认忽略这类文件，提交前仍应人工复核。

## 资料与商标

仓库只包含根据本地 xRobotDesigner 帮助资料整理的精简说明，不分发原始 CHM、PDF
或厂商软件。请在自身授权范围内使用本机安装的原始资料。Kecon、xRobotDesigner
及相关名称和商标归其各自权利人所有；本项目并非官方产品。
