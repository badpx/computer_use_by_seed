# Computer Use Tool

基于火山方舟模型的本地 GUI 自动化工具。

## 功能特性

- 🤖 **多轮自动执行** - 自动循环执行直到任务完成
- 🖱️ **丰富操作支持** - 点击、输入、滚动、拖拽、热键等
- 📸 **截图保存** - 支持开关配置，便于调试
- 🧾 **上下文日志** - 保存每轮模型输入与执行结果，便于回放调试
- ⚙️ **灵活配置** - 支持环境变量和配置文件
- 💻 **CLI 交互** - 支持交互式和单次任务模式

## 环境要求

- **操作系统**: macOS / Windows / Linux
- **Python**: 3.8 - 3.13
- **网络**: 可访问火山方舟 API

> 目前不建议使用 Python 3.14+。
> `volcengine-python-sdk[ark]` 依赖 `pydantic.v1` 兼容层，而该兼容层在 Python 3.14+ 上会触发兼容性告警，且不保证可正常工作。

## 快速开始

### 1. 创建虚拟环境

```bash
# 创建虚拟环境
python3.13 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
```

如果你的机器默认 `python` 已经是 3.13，也可以使用：

```bash
python -m venv venv
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API 密钥

#### 方式一：环境变量（推荐）

```bash
export ARK_API_KEY="your_api_key_here"
```

#### 方式二：配置文件

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```

### 4. 运行

#### 交互模式

```bash
python -m computer_use
```

交互模式默认使用 `prompt_toolkit`，支持：

- 上下键切换历史输入
- 左右键编辑当前输入
- 直接粘贴长文本
- 历史记录持久化到 `~/.computer_use_history`
- 输入 slash 命令并自动补齐命令名，例如 `/status`、`/display`、`/clear`、`/compact`、`/exit`

如果运行环境中缺少 `prompt_toolkit`，CLI 会自动回退到基础 `input()` 模式。

#### 单次任务

```bash
python -m computer_use "打开浏览器"
```

## 配置说明

### 配置优先级

配置加载遵循以下优先级（从高到低）：

1. **环境变量** - 最高优先级
2. **配置文件** (`.env`) - 中等优先级
3. **代码默认值** - 最低优先级

### 配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| API 密钥 | `ARK_API_KEY` | - | **必需**，火山方舟 API 密钥 |
| 模型名称 | `ARK_MODEL` | `doubao-seed-1-6-vision-250815` | 使用的模型 |
| API 地址 | `ARK_BASE_URL` | `http://ark.cn-beijing.volces.com/api/v3` | API 基础 URL |
| 温度参数 | `TEMPERATURE` | `0.0` | 模型温度参数 |
| 思考模式 | `THINKING_MODE` | `auto` | 方舟思考模式，可选 `enabled` / `disabled` / `auto` |
| 思考档位 | `REASONING_EFFORT` | `medium` | 方舟思考档位，可选 `minimal` / `low` / `medium` / `high` |
| 坐标空间 | `COORDINATE_SPACE` | `relative` | 坐标空间，可选 `relative` / `pixel` |
| 坐标量程 | `COORDINATE_SCALE` | `1000` | `relative` 坐标的量程，例如 `1` / `100` / `1000` |
| 目标显示器 | `DISPLAY_INDEX` | `0` | 截图和动作执行所使用的显示器编号，`0` 表示主显示器 |
| 模型截图尺寸 | `SCREENSHOT_SIZE` | - | 传给模型前的截图宽高，仅支持相同宽高值，例如 `1024` 表示缩放为 `1024x1024` |
| 上下文截图窗口 | `MAX_CONTEXT_SCREENSHOTS` | `5` | 多轮上下文中最多保留的截图数量，包含当前轮 |
| 注入执行反馈 | `INCLUDE_EXECUTION_FEEDBACK` | `false` | 是否将历史执行结果和失败原因注入多轮上下文 |
| 最大步数 | `MAX_STEPS` | `100` | 最大执行步数 |
| 自然滚动 | `NATURAL_SCROLL` | 自动检测 | 是否按系统自然滚动方向解释 scroll 偏移 |
| 保存上下文日志 | `SAVE_CONTEXT_LOG` | `true` | 是否保存每任务 JSONL 调试日志 |
| 日志目录 | `CONTEXT_LOG_DIR` | `./logs` | 上下文日志保存目录 |

### `.env` 文件示例

```bash
# 必需配置
ARK_API_KEY=your_api_key_here

# 可选配置
ARK_MODEL=doubao-seed-1-6-vision-250815
ARK_BASE_URL=http://ark.cn-beijing.volces.com/api/v3
TEMPERATURE=0.0
THINKING_MODE=auto
REASONING_EFFORT=medium
COORDINATE_SPACE=relative
COORDINATE_SCALE=1000
DISPLAY_INDEX=0
SCREENSHOT_SIZE=
MAX_CONTEXT_SCREENSHOTS=5
INCLUDE_EXECUTION_FEEDBACK=false
MAX_STEPS=100

# 滚动方向；留空时自动检测系统设置
NATURAL_SCROLL=

# 调试日志配置
SAVE_CONTEXT_LOG=true
CONTEXT_LOG_DIR=./logs
```

### 历史上下文组织

每一轮调用方舟模型时，代理会发送：

- 单独一份 system 提示词
- 会话历史中的用户指令消息
- 会话历史中的 assistant 历史响应
- 已展开并持久生效的 skill 指令消息
- 最近 `N` 张截图对应的图片消息，默认最多 5 张，包含当前轮
- 可选的历史执行反馈文本

上下文裁剪规则：

- 文本消息默认全部保留，包括用户指令、assistant 响应、skill 指令和执行反馈
- 图片消息只保留最近 `MAX_CONTEXT_SCREENSHOTS` 张，包含当前截图
- 执行反馈默认关闭，可通过 `INCLUDE_EXECUTION_FEEDBACK` 或 CLI 开启
- 当估算上下文占用超过窗口的 90% 时，会按用户指令 turn 自动压缩旧历史：把旧的 `user / assistant / feedback` 总结成更短的 `user + assistant` pair，并丢弃旧截图

历史截图优先保存在限长内存队列中，不依赖本地截图文件回放。传 `--verbose` 时，工具会把传给模型的截图保存到 `CONTEXT_LOG_DIR/screenshots/`，并在 JSONL 日志中以相对路径引用这些图片，而不是内联 base64 数据，方便调试和回放。

如果设置了 `SCREENSHOT_SIZE` 或 `--screenshot-size`，工具会先把屏幕截图强制缩放为 `NxN` 再传给模型。目前仅支持宽高相同的正方形尺寸。启用后，`pixel` 坐标会按“模型图尺寸 -> 真实屏幕尺寸”自动换算，避免点击偏移。

如果设置了 `DISPLAY_INDEX` 或 `--display-index`，工具会只截取该显示器的画面，并将模型输出的局部坐标自动换算到虚拟桌面绝对坐标后再执行点击、拖拽和滚动。交互模式下还可以通过 `/display <index>` 运行时切换目标显示器，成功后会同步写回项目 `.env`。

交互模式下：

- 可通过 `/status` 查看本次会话真正生效的参数
- 可通过 `/display <index>` 切换当前交互会话的目标显示器，并持久化到项目 `.env`
- 可通过 `/clear` 清空当前交互会话的多轮上下文历史
- 可通过 `/compact` 手动压缩当前交互会话的旧历史文本上下文
- 多条用户输入会持续追加到同一会话历史中，而不是按输入重置上下文
- skill 一旦在当前交互会话中展开，会转成普通用户消息持久保留并持续生效
- 传 `--verbose` 时，额外打印 `[配置信息]`，用于展示基础环境和调试相关配置

## CLI 参数

```
python -m computer_use [指令] [选项]
```

### 位置参数

| 参数 | 说明 |
|------|------|
| `instruction` | 任务指令（可选，不提供则进入交互模式） |

### 可选参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--model` | `-m` | 指定模型名称 |
| `--max-steps` | `-s` | 指定最大执行步数 |
| `--thinking <mode>` | `-t` | 设置方舟思考模式，取值 `enabled` / `disabled` / `auto` |
| `--reasoning-effort <level>` | `-r` | 设置方舟思考档位，取值 `minimal` / `low` / `medium` / `high` |
| `--coordinate-space <space>` | - | 设置坐标空间，取值 `relative` / `pixel` |
| `--coordinate-scale <value>` | - | 设置 `relative` 坐标量程，例如 `1` / `100` / `1000` |
| `--display-index <index>` | - | 设置目标显示器编号，`0` 表示主显示器 |
| `--screenshot-size <value>` | - | 设置传给模型的截图宽高，仅支持正方形，例如 `1024` 表示 `1024x1024` |
| `--max-context-screenshots <count>` | - | 设置多轮上下文中保留的截图数量，包含当前轮 |
| `--include-execution-feedback` | - | 启用执行反馈注入 |
| `--no-execution-feedback` | - | 禁用执行反馈注入 |
| `--verbose` | - | 在上下文日志中记录完整 `messages`，并将截图保存到 `CONTEXT_LOG_DIR/screenshots/` |
| `--natural-scroll` | - | 显式启用自然滚动 |
| `--traditional-scroll` | - | 显式启用传统滚动 |
| `--quiet` | `-q` | 安静模式，减少输出 |
| `--version` | `-v` | 显示版本信息 |
| `--help` | `-h` | 显示帮助信息 |

### 使用示例

```bash
# 交互模式
python -m computer_use

# 单次任务
python -m computer_use "打开浏览器"

# 指定模型
python -m computer_use "打开微信" --model doubao-seed-1-6-vision-250815

# 指定第 2 台显示器作为目标屏幕
python -m computer_use "打开微信" --display-index 1

# 指定最大步数
python -m computer_use "搜索 Python 教程" --max-steps 10

# 保留最近 3 张截图上下文
python -m computer_use "分析页面状态" --max-context-screenshots 3

# 将传给模型的截图缩放为 1024x1024
python -m computer_use "分析页面状态" --screenshot-size 1024

# 关闭执行反馈注入
python -m computer_use "打开浏览器" --no-execution-feedback

# 在上下文日志中记录完整 messages
python -m computer_use "分析页面状态" --verbose

# 显式启用思考模式
python -m computer_use "分析这个页面并给出下一步操作" --thinking enabled

# 使用短参数并禁用思考
python -m computer_use "打开浏览器" -t disabled

# 设置低档位思考
python -m computer_use "总结这个页面" -t enabled -r low

# Kimi [0,1] 坐标输出
python -m computer_use "点击按钮" --coordinate-space relative --coordinate-scale 1

# 原生像素坐标输出
python -m computer_use "点击按钮" --coordinate-space pixel

# 强制使用传统滚动
python -m computer_use "浏览网页" --traditional-scroll

# 安静模式
python -m computer_use "打开记事本" --quiet
```

## 支持的操作

| 操作类型 | 说明 | 示例 |
|----------|------|------|
| `click` / `left_single` | 左键单击 | `click(point='<point>100 200</point>')` |
| `left_double` | 左键双击 | `left_double(point='<point>100 200</point>')` |
| `right_single` | 右键单击 | `right_single(point='<point>100 200</point>')` |
| `hover` | 鼠标悬停 | `hover(point='<point>100 200</point>')` |
| `drag` | 拖拽 | `drag(start_point='<point>100 200</point>', end_point='<point>300 400</point>')` |
| `hotkey` | 热键组合 | `hotkey(key='ctrl c')` |
| `press` / `keydown` | 按下按键 | `press(key='enter')` |
| `release` / `keyup` | 释放按键 | `release(key='enter')` |
| `type` | 输入文本 | `type(content='Hello World')` |
| `scroll` | 滚动 | `scroll(point='<point>500 500</point>', direction='down')` |
| `wait` | 等待 | `wait()` |
| `finished` | 任务完成 | `finished(content='任务完成')` |

## 注意事项

1. **API 密钥安全** - 不要将 API 密钥提交到版本控制中，使用 `.gitignore` 忽略 `.env` 文件

2. **屏幕分辨率** - 工具会根据截图自动适配屏幕分辨率，请确保截图时屏幕分辨率稳定

3. **操作安全** - 工具会实际控制鼠标和键盘，请确保在安全的测试环境中使用

4. **网络连接** - 需要稳定的网络连接到火山方舟 API

5. **依赖安装** - 某些系统可能需要额外安装依赖，如 Linux 系统可能需要 `scrot` 用于截图

## 故障排除

### 常见问题

**Q: 运行时出现 `Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater` 告警怎么办？**
A: 这是 `volcengine-python-sdk[ark]` 依赖链触发的兼容性告警，不是本项目自己的逻辑问题。请改用 Python 3.13 或更低版本重新创建虚拟环境，例如：

```bash
rm -rf venv
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Q: 启动时提示缺少 API 密钥**
A: 请设置 `ARK_API_KEY` 环境变量或创建 `.env` 文件

**Q: 模型调用失败**
A: 请检查网络连接和 API 密钥是否正确，以及模型名称是否有效

**Q: 截图失败**
A: 请检查屏幕权限设置，某些系统需要授权才能截图

**Q: 鼠标/键盘操作无效**
A: 请检查是否有其他应用占用了输入控制权

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题或建议，请通过 GitHub Issues 联系我们。
