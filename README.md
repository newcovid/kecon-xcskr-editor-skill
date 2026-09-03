# Kecon xRobotDesigner `.xcskr` Editor Skill

一个面向 Claude Code / Codex 的非官方 Skill，用于检查、摘要、导出和安全修改科聪
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
- 定点修改变量、POU、硬件标签、CAN/CANopen 对象和映射属性。改结构体成员的 DESC 只动类型
  那一份，每个变量还留着一份旧文本，必须跟一次 `rebuild-variable-members`；工程照样编译运行，
  没有任何东西会报，`validate-desc-drift` 专抓这个。
- 重命名硬件标签时，同时移动它的 `VARIABLE_MEMBER` 成员树和命令组引用——ST 引用的是成员。
- 重命名 POU（`rename-pou`）：程序只改自己的标识；功能块连 ST 调用点和图形块 `TYPE` 一起改。
- 删除 POU、结构体成员、CANopen 从站对象（`remove --kind pou / user-struct-member / slave-object`）：
  先扫 ST、图形绑定、Modbus 映射、命令组里的引用，有引用就拒绝，`--force` 才放行；
  删结构体成员会顺手重建承载它的变量成员树并保留逐元素 DESC。
- 给启用的 CANopen 命令组补发命令号。GUI 勾选时会自动发号，直接改 XML 不会；
  少了号编译器不报命令组，而是报引用该标签的**程序**「字符串无法识别」并算在第 1 行。
- 创建时间戳备份。

### 静态检查

写进去能编译、能下载、能运行，但在别处出问题的那一类，都做成了校验器。
`check-workspace` 一次跑完并输出成 `file:line:col`：

| 检查 | 它挡住的是 |
|---|---|
| `validate-datatypes` | 结构体改过之后，变量的成员树没跟着重建 |
| `validate-st-format` | 多语句 ST 缺少原始 XML 换行，GUI 里显示成一行 |
| `validate-canopen-command-ids` | 命令号重复；`alloc-canopen-command-ids` 给启用了却没号的补发 |
| `validate-hardware-bindings` | 命令组指向的通道标签不存在或没启用 |
| `validate-slave-objects` | 从站对象名、数据类型、绑定预算三项 GUI 才校验的限制 |
| `validate-command-directions` | 读从站数据的命令组被留成了输出命令 -- 导入 EDS 会静默改回去 |
| `validate-fb-calls` | 功能块调用的实参顺序与声明顺序不一致 |
| `validate-desc-length` | 超长 DESC。XML 收，GUI 下次打开那个字段就再也保存不了 |
| `validate-array-index` | 位串当数组下标 |
| `validate-comment-balance` | 没闭合的 `(*` 把后面整段代码吃掉，编译不报错 |
| `validate-modbus-mapping` | 映射窗口里标签宽度与地址空间对不上，编译只报窗口名不报标签 |
| `validate-desc-drift` | 改了结构体成员的 DESC 却没重建变量成员树，监控里还显示旧文本 |
| `validate-controller-support` | 用了本型号控制器不支持的功能 |

### 写入保真

读写均关闭换行转换，生成的 XML 复现 GUI 的属性集合、字母序属性顺序和自闭合写法，
缩进步长从目标文件读取。对官方样例工程做“解绑再绑回”“拆线再接回”的往返测试，
结果与原件逐字节一致。

XML 结构约定每条都记着它的来源：与官方示例工程逐项核对、GUI 实测、生产工程复现，
或者看编译器收不收。请按每条注明的方式判断可信度，没标的就是推断。详见 [`references/xcskr-structure.md`](kecon-xcskr-editor/references/xcskr-structure.md)
和 [`references/ld-fbd-st.md`](kecon-xcskr-editor/references/ld-fbd-st.md)。

## 文本工作区：在 GUI 之外编辑

xRobotDesigner 的编辑器不能改字体、字号和配色，工程一大就很难写。
`xcskr_workspace.py` 把工程摊成一棵文本目录：每个 POU 一个 `.st`，图形 POU 一个
`.graph.json`，另有只读的变量表、结构体表和符号表。改完一次性回灌，单次写入并自动备份。

```powershell
python scripts\xcskr_workspace.py export-workspace --project P --workspace W
python scripts\xcskr_workspace.py import-workspace --project P --workspace W --dry-run
python scripts\xcskr_workspace.py import-workspace --project P --workspace W
python scripts\xcskr_workspace.py check-workspace  --project P --workspace W
```

四条拒绝构成它的安全边界：工程在导出之后被改过（GUI 保存会整份覆盖文件）、
导出会冲掉尚未回灌的编辑（这些文件会先存进 `_ws/.discarded/`）、工作区文件被改名、
以及图形改动超出「引脚绑定 / 初值 / 取反、块停用、连线增删」的范围--
块的 `TYPE` 隐含一张文件里没有的固定引脚表，所以新块只能用 `copy-block` 从参考工程复制。

`check-workspace` 把各项校验的结果输出成 `file:line:col`，可直接接编辑器的问题面板。

## 本机路径配置

安装目录、帮助文件和样例工程的位置每台机器都不同，任何一处都不写死在代码里。
解析顺序是 **命令行参数 -> 环境变量 -> 配置文件 -> 内置探测**。

```powershell
Copy-Item kecon-xcskr-editor\kecon-resources.example.json kecon-xcskr-editor\kecon-resources.json
python scripts\xcskr_tool.py resources          # 看每个值最终取自哪里
```

`kecon-resources.json` 已在 `.gitignore` 中，**不要提交**--它记录的是个人目录结构。

## 仓库结构

```text
kecon-xcskr-editor-skill/
├── README.md
├── .gitignore
└── kecon-xcskr-editor/
    ├── SKILL.md
    ├── kecon-resources.example.json   本机路径示例，复制成 kecon-resources.json 后使用
    ├── agents/
    ├── references/
    ├── scripts/
    │   ├── xcskr_tool.py              读写工程与静态检查
    │   ├── xcskr_workspace.py         文本工作区导出/回灌
    │   └── kecon_help.py              本机帮助原文检索
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
