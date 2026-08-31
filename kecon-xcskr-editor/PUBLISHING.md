# 发布到公开仓库

公开仓库是 <https://github.com/newcovid/kecon-xcskr-editor-skill>，
在本地配成 `public` 远端（**不是** `origin`，就是为了提醒它不能直接推）。

## 为什么不能 `git push`

两边**不是同一份历史**，`git merge-base` 查不到共同祖先，布局也不一样：

```text
本地（这个仓库）          公开仓库
SKILL.md                  README.md                    <- 面向使用者的门面，本地没有
scripts/                  .gitignore
references/               kecon-xcskr-editor/          <- 本地这一整棵树装在这里
tests/                      SKILL.md
README.md                   scripts/  references/  tests/
```

公开仓库是个**外壳**：顶层放 README 和 `.gitignore`，技能装在
`kecon-xcskr-editor/` 子目录里，因为使用者要把那个子目录整个复制进
`~/.codex/skills`。直接 `git push --force` 会把布局压平、删掉顶层 README，
把公开仓库毁掉。

## 正确做法

在临时目录里克隆公开仓库，用本地 **HEAD 的已跟踪文件**覆盖子目录，
再在公开仓库自己的历史上提交：

```powershell
git clone https://github.com/newcovid/kecon-xcskr-editor-skill.git $env:TEMP\pub
cd $env:TEMP\pub
git rm -r -q kecon-xcskr-editor
mkdir kecon-xcskr-editor
git -C <本地技能目录> archive HEAD | tar -x -C kecon-xcskr-editor
```

用 `git archive HEAD` 而不是复制目录：它只吐出已跟踪的文件，
`__pycache__`、`kecon-resources.json`、`*.bak_*` 一个都进不去。

然后：

1. 跑一遍测试确认打包完整：`cd kecon-xcskr-editor; python -m unittest discover -s tests`
2. 顶层 `README.md` 有新功能就补上，`.gitignore` 有新的本机文件类型就补上
3. 提交、推送

## 不写日期

技能里**一处日期都不许有**，包括 `*Verified <年-月-日>: …*` 这种证据标注。
（这里故意不写成真日期，否则下面那条守卫 grep 会永远报自己一条，久了就没人看了。）
证据等级要留（`verified` / `未验证`），**验证方式**也要留 —— 那是别人判断可信度的依据；
但「哪天验的」对用它的人没有用，只会让人去算这条过没过期。同理不写变更史，
只陈述事实和提供工具，历史在 git log 里。

```powershell
git grep -nE "20[0-9]{2}-[0-9]{2}-[0-9]{2}|20[0-9]{2}年"
```

## 每次发布前必做的脱敏检查

工程文件里有客户名、设备地址、工艺参数，技能的文档和注释里很容易顺手带出来。
公开仓库到目前为止**没有出现过任何客户或个人标识**，要保持这一点：

```powershell
git grep -nE "客户名|项目名|人名|C:\\Users|D:\\<个人目录>"
```

- **本机路径一律不写死**。安装目录、帮助文件、样例工程的位置走
  `kecon-resources.json`（已 git 忽略，只提交 `.example.json`），
  解析顺序是 命令行参数 -> 环境变量 -> 配置文件 -> 内置探测。
  唯一允许出现在代码里的绝对路径是 `D:\KCSmart\xRobotDesigner` 这类
  **厂商默认安装路径**，那在每台装了 xRobotDesigner 的机器上都一样，不是个人信息。
- **举例子不要带项目名**。修过一处：把「the <某项目> project's
  `底盘控制`」改成「a production project's `底盘控制`」——
  技术要点是「这个 POU 只有一个 78 引脚的厂商块、零连线」，跟它出自哪个项目无关。
- **`*.xcskr` 在两边的 `.gitignore` 里都是忽略的**，别为了做样例把真工程放进去，
  见下一节。

## 样例工程：目前是空缺

公开仓库现在没有任何可运行的样例，测试用的是代码里现搭的最小工程
（`tests/test_xcskr_tool.py` 的 `make_project`）。这带来两个问题：

- README 里「对官方样例工程做往返测试，逐字节一致」这句话，别人**无法复现**——
  官方样例只在装了 xRobotDesigner 的机器上有。
- 新用户 clone 下来没有任何东西可以拿来试手。

建议的方向（按优先级）：

1. **自己合成一个厂商中立的 `.xcskr` 夹具**，用脚本生成而不是从任何真工程裁剪：
   一个 CAN 口、两个从站、几个带命令号的命令组、一个 ST 程序、一个 FBD POU。
   它不来自客户也不来自厂商，可以放心提交（需要在 `.gitignore` 里为
   `tests/fixtures/*.xcskr` 开个白名单口子）。
2. **把往返保真做成金标准测试**：夹具 + 期望导出结果一起入库，
   断言「导出再回灌」与原件逐字节一致。现在这条保证只存在于 README 的说法里。
3. **官方样例工程不要入库**，版权归厂商。改为提供一条针对本机官方样例跑的冒烟命令
   （读 `kecon-resources.json` 的 `sample_projects`），让别人在自己机器上验证保真度。
4. 客户工程**永远不入库**，包括裁剪过的。裁剪很难裁干净，命令组名、结构体名、
   报警文案都会带信息出去。
