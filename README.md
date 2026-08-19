# Kecon xRobotDesigner `.xcskr` Editor Skill

一个面向 Codex 的非官方 Skill，用于检查、摘要、导出和安全修改科聪
xRobotDesigner `.xcskr` PLC 工程。

## 功能

### 读取

- 将 GBK XML 工程导出为紧凑的 AI 可读结构包。
- 检查控制方案、任务、程序、功能块、变量和用户数据类型。
- 导出 LD/FBD 的块、引脚、连接（区分变量绑定与连线）、连线和注释结构。
- 提取 ST 源码。
- 检索本机 xRobotDesigner 帮助原文（见下方“帮助原文检索”）。

### 写入

- 新建 PROGRAM、调整任务内程序执行顺序（程序按文档顺序执行，顺序即语义）。
- 新建 FUNCTION_BLOCK 及其接口变量，追加 POU 接口变量。
- 新建用户数据类型和自定义变量，自动生成 VARIABLE_MEMBER 成员树；结构体改动后可用
  `rebuild-variable-members` 重建，`validate-datatypes` 递归查成员树漂移。
- 图形逻辑：引脚绑定变量、两引脚连线、拆线、从参考工程复制功能块。
- 替换 ST，保留该 POU 或工程原有的换行编码风格。
- 定点修改变量、POU、硬件标签、CAN/CANopen 对象和映射属性。
- 创建时间戳备份，并提供 ST 格式、数据类型、CANopen 命令 ID 静态检查。

### 写入保真

读写均关闭换行转换，生成的 XML 复现 GUI 的属性集合、字母序属性顺序和自闭合写法，
缩进步长从目标文件读取。对官方样例工程做“解绑再绑回”“拆线再接回”的往返测试，
结果与原件逐字节一致。

XML 结构约定不是从单个工程猜的，而是与 xRobotDesigner 随附的官方示例工程逐项核对过，
详见 [`references/xcskr-structure.md`](kecon-xcskr-editor/references/xcskr-structure.md)
和 [`references/ld-fbd-st.md`](kecon-xcskr-editor/references/ld-fbd-st.md)。

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

## 帮助原文检索

`kecon_help.py` 同时检索随 Skill 提供的精简知识库，以及从本机 xRobotDesigner
帮助 CHM 建立的原文索引。建索引使用 Windows 自带的 `hh.exe -decompile`，无需安装
任何依赖；Word 导出的表格会压成管道分隔行，因此功能块参数表可以直接读；`.hhc`
目录文件提供每个主题的真实标题和层级路径。

```powershell
python ".\kecon-xcskr-editor\scripts\kecon_help.py" status
python ".\kecon-xcskr-editor\scripts\kecon_help.py" index --chm "<xCSStudioHelpFile.chm 的本机路径>"
python ".\kecon-xcskr-editor\scripts\kecon_help.py" search "八差速 底盘"
python ".\kecon-xcskr-editor\scripts\kecon_help.py" show 八差速_舵轮总成底盘
```

索引只缓存纯文本，默认放在 `~/.kecon-xcskr-editor/help`，可用 `--cache-dir` 或环境
变量 `KECON_HELP_CACHE` 改位置。**官方帮助原文只留在本机，不进入本仓库。**

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
