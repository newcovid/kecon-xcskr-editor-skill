# Kecon xRobotDesigner Help KB

这是从 xRobotDesigner 随附的 CHM/PDF 帮助中提炼的轻量知识库。执行科聪相关任务时，先查这里；这里找不到再查用户本机已授权的原文。

原始资料不随本 Skill 分发。不同版本和安装方式的帮助目录可能不同；需要兜底查询时，先让用户确认本机 CHM/PDF 的实际路径。

## 目录

- 查询流程
- 工程、控制方案与任务
- 程序、功能块与 ST 调用
- 基本功能块库
- CAN 与 CANopen 通讯
- 串口、Modbus 与安全 PLC
- 导航、底盘与运动分解
- 机器人模型组态向导 PDF
- 原文兜底查询

## 查询流程

先运行：

```powershell
python (Join-Path $keconSkillDir "scripts\kecon_help.py") search "关键词"
```

关键词可用中文或英文，例如：`功能块`、`CAN`、`CANopen`、`Modbus`、`主任务`、`周期任务`、`事件任务`、`安全IO`、`导航`、`底盘`、`模型组态`。

如果命中信息不足，再查原文。CHM 可用 `hh.exe -decompile <输出目录> <chm路径>` 反编译后搜索 HTML；PDF 可用 `pypdf` 或 PyMuPDF 提取文本。

## 工程、控制方案与任务

xRobotDesigner 工程中的控制程序不应只按顶层 POU 理解。实际 `.xcskr` 结构里，程序位于控制器硬件节点下的 `CONTROL_SCHEME`，任务节点可包含：

- `MAIN_TASK`：主任务，可挂多个 `PROGRAM`。
- `EVENT_TASK`：事件任务，常见触发条件在 `TRIG_CONDITION`，例如 DI 上升沿。
- `CYCLE_TASK`：周期任务，可单独挂程序，适合周期通讯或低频处理。

做程序梳理时先看控制方案下的任务，再看每个任务下的 `PROGRAM`；不要只用 `PROGRAM` 全局列表替代任务结构。

原文线索：CHM 中有“启动任务”“导入/导出程序”“删除程序”“变量调试”等条目；XML 结构需以实际工程导出的 `index.json` 为准。

## 程序、功能块与 ST 调用

功能块在帮助中被描述为带输入/输出引脚的图形块；使用 ST 时可以调用系统功能块，也可以调用自定义功能块。调用方式通常是功能块实例名加圆括号参数映射。

在自写逻辑前，先查已有功能块或系统库，避免重复造轮子。尤其是通讯、导航、底盘运动分解、安全 IO、音频、充电、手操器解析等任务，帮助中已有大量功能块条目。

原文线索：CHM 条目“功能块”“功能块调用”“功能块引脚编辑”“基本功能块库”。

## 基本功能块库

CHM 的“基本功能块库”覆盖常用逻辑运算、定时计数、比较选择、数学运算、高级数学、通信处理、信号控制等类别。常见计数/定时类如 `CTUD` 等在原文中有独立条目。

优先复用基本库：
- 逻辑、比较、选择、数学、转换类功能。
- 定时器、计数器、触发类功能。
- 通信读写与信号处理功能。

原文线索：CHM 条目“基本功能块库”“CTUD增减计数器”“功能块调用”。

## CAN 与 CANopen 通讯

CHM 中“CAN通讯接口设备接入组态”说明控制器可为驱动器和其他 CAN 设备配置 CAN 总线；组态界面可设置波特率、周期间隔并查看总线负载等信息。具体工程里的 XML 端口名称、显示名和物理端口不一定一致，必须以 `export-ai` 导出的 `hardware.json` 为准。

已有功能块/条目包括：
- `CAN读（扩展帧）`
- `CAN写（扩展帧）`
- CAN 通讯接口设备接入组态

做 CAN/CANopen 任务时先导出 `hardware.json`，查看 `downlink_ports`、`stations`、`hardware_tags`、`slave_objects` 和 `slave_mappings`，再决定是否需要改硬件变量或对象字典。

原文线索：CHM 条目“CAN通讯接口设备接入组态”“CAN读（扩展帧）”“CAN写（扩展帧）”。

## 串口、Modbus 与安全 PLC

CHM 中有自定义串口通信组态、串口调试、Modbus RTU 读取安全 PLC 状态等内容。安全相关条目通常通过非安全 PLC 读取安全 PLC 或安全模块数据，不应把安全功能直接等同于普通 DI/DO。

已有功能块/条目包括：
- 自定义串口通信组态
- 串口调试
- 安全状态
- 安全 IO
- 安全避障信息设置

做 RS485/Modbus/安全 IO 任务时先查这些条目，确认已有功能块和变量接口，再写自定义逻辑。

## 导航、底盘与运动分解

CHM 有大量导航和底盘相关功能块条目，适合先查后复用：

- 导航：激光导航、二维码导航、磁导航、GNSS 数据上送、混合导航状态/控制命令。
- 底盘：双舵轮、三舵轮、四舵轮、六舵轮、八舵轮、差速/舵轮总成、全向轮等运动分解功能块。
- 辅助：运动通道选择、导航模式管理、获取导航信息、获取避障状态、设置避障区域组。

这些条目的共同模式是：上游导航功能块输出线速度、角速度、横移速度或任务状态；底盘/运动分解功能块再按机构几何、反馈角度、里程等计算电机或舵轮命令。

原文线索：CHM 条目“激光导航”“二维码导航”“半自动磁导航”“GNSS数据上送”“八舵轮底盘”“八差速/舵轮总成底盘”“运动通道选择”。

## 机器人模型组态向导 PDF

PDF《机器人模型组态向导用户使用手册》主要用于模型/参数组态，不是 `.xcskr` XML 结构说明。它适合查：

- 新建工程和模型库/云端模型库。
- 新建或导入用户自定义车型。
- 底盘参数、导航参数、传感器参数。
- 自定义电池、手操器、混合导航与导航状态。
- 模型参数配置、测试调试、部署流程。

当任务是“工程 XML 读写”时优先用 `xcskr_tool.py export-ai`；当任务是“机器人模型/参数怎么配置”时再查该 PDF。

## 原文兜底查询

当本 KB 找不到答案时，按下面方式查原文。

先设置用户本机实际存在的原文路径：

```powershell
$chmPath = "<path-to-xCSStudioHelpFile.chm>"
$pdfPath = "<path-to-机器人模型组态向导用户使用手册.pdf>"
```

CHM：

```powershell
$out = Join-Path $env:TEMP ("kecon_chm_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $out | Out-Null
& "$env:WINDIR\hh.exe" -decompile $out $chmPath
rg -n "关键词" $out
```

PDF：

```powershell
@'
import sys
from pathlib import Path
from pypdf import PdfReader
p = Path(sys.argv[1])
reader = PdfReader(str(p))
for i, page in enumerate(reader.pages, 1):
    text = page.extract_text() or ""
    if "关键词" in text:
        print(i, text[:1000])
'@ | python - $pdfPath
```

如果环境中没有 `pypdf`，可改用已有的 PDF 文本提取工具；不要为查询帮助资料修改原始 PDF。
