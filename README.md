# Computer Use Tool

基于 OpenAI SDK 的 GUI 自动化工具。默认可直接操控本地桌面，也支持通过设备插件连接 Android 手机、VNC 远程桌面等其他环境。默认 provider 为 Ark，并通过兼容 OpenAI API 的方式调用模型。

## 你可以先这样用

### 1. 创建虚拟环境并安装依赖

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

如果你的机器默认 `python` 已经是 3.13，也可以使用：

```bash
python -m venv venv
```

### 2. 配置 API 密钥

方式一：环境变量

```bash
export API_KEY="your_api_key_here"
```

方式二：配置文件

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥
```

### 3. 检查运行环境

```bash
python check_env.py
```

### 4. 运行

交互模式：

```bash
python -m computer_use
```

单次任务：

```bash
python -m computer_use "打开浏览器"
```

## 核心能力

- 多轮自动执行，直到任务完成或达到步数上限
- 支持点击、输入、滚动、拖拽、热键等常见 GUI 动作
- 支持交互模式和单次任务模式
- 支持 JSONL 上下文日志，便于调试和回放
- 支持设备插件，可切换本地桌面、Android、VNC 等不同控制目标

## 环境要求

- 操作系统：macOS / Windows / Linux
- Python：3.8 - 3.13
- 网络：可访问模型服务 API

## 最常用的运行方式

### 交互模式

```bash
python -m computer_use
```

交互模式默认使用 `prompt_toolkit`，支持：

- 上下键切换历史输入
- 左右键编辑当前输入
- 直接粘贴长文本
- 历史记录持久化到 `~/.computer_use_history`
- slash 命令自动补齐，例如 `/status`、`/display`、`/clear`、`/compact`、`/exit`

如果运行环境中缺少 `prompt_toolkit`，CLI 会自动回退到基础 `input()` 模式。

### 单次任务模式

```bash
python -m computer_use "打开浏览器"
```

默认情况下，单次任务模式不会向用户发起 `ask_user` 询问。
如果需要在单次任务中启用 Human-in-the-loop 询问，可在 `.env` 或环境变量中设置 `ENABLE_ASK_USER_FOR_SINGLE_TASK=true`。

### 常见示例

```bash
# 指定模型
python -m computer_use "打开微信" --model doubao-seed-1-6-vision-250815

# 指定最大步数
python -m computer_use "搜索 Python 教程" --max-steps 10

# 指定第 2 台显示器作为目标屏幕（仅对支持目标切换的设备生效）
python -m computer_use "打开微信" --display-index 1

# 将传给模型的截图缩放为 1024x1024
python -m computer_use "分析页面状态" --screenshot-size 1024

# 关闭成功执行反馈注入（失败反馈仍会保留）
python -m computer_use "打开浏览器" --no-execution-feedback

# 在上下文日志中记录完整 messages
python -m computer_use "分析页面状态" --verbose
```

## 配置方式

配置优先级如下：

1. 环境变量
2. 配置文件 `.env`
3. 代码默认值

### 常用配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| API 密钥 | `API_KEY` | - | 必需，模型服务 API 密钥 |
| Provider | `PROVIDER` | `ark` | 当前 provider profile |
| 模型名称 | `MODEL` | `doubao-seed-1-6-vision-250815` | 使用的模型 |
| API 地址 | `BASE_URL` | 按 provider 取默认值 | API 基础 URL |
| Provider 配置 | `PROVIDER_CONFIG_JSON` | - | provider 私有 JSON 配置，例如 OpenRouter headers |
| 流式响应 | `STREAM` | - | 是否向模型调用显式传入 `stream=true/false`；未配置时不传 |
| 最大输出长度 | `MAX_TOKENS` | - | 主任务模型调用的 `max_tokens`；未配置时不传 |
| 设备插件 | `DEVICE_NAME` | `local` | 当前设备适配器 |
| 设备配置 | `DEVICE_CONFIG_JSON` | - | 设备插件私有 JSON 配置 |
| 目标显示器 | `DISPLAY_INDEX` | `0` | 仅对支持目标切换的设备生效；`local` 会把它解释为显示器编号 |
| 模型截图尺寸 | `SCREENSHOT_SIZE` | - | 传给模型前的截图宽高，仅支持正方形 |
| 上下文截图窗口 | `MAX_CONTEXT_SCREENSHOTS` | `5` | 多轮上下文中保留的截图数量，包含当前轮 |
| 注入执行反馈 | `INCLUDE_EXECUTION_FEEDBACK` | `false` | 是否将成功执行结果注入上下文；失败反馈始终会注入 |
| 最大步数 | `MAX_STEPS` | `100` | 最大执行步数 |
| 自然滚动 | `NATURAL_SCROLL` | 自动检测 | 是否按系统自然滚动方向解释 `scroll` 动作 |
| 保存上下文日志 | `SAVE_CONTEXT_LOG` | `true` | 是否保存每任务 JSONL 调试日志 |
| 日志目录 | `CONTEXT_LOG_DIR` | `./logs` | 上下文日志保存目录 |
| 单次任务启用询问用户 | `ENABLE_ASK_USER_FOR_SINGLE_TASK` | `false` | 是否允许单次任务模式使用 `ask_user` 能力 |

### `.env` 示例

```bash
API_KEY=your_api_key_here
PROVIDER=ark
BASE_URL=http://ark.cn-beijing.volces.com/api/v3
MODEL=doubao-seed-1-6-vision-250815
PROVIDER_CONFIG_JSON=
STREAM=
MAX_TOKENS=
DEVICE_NAME=local
DEVICE_CONFIG_JSON=
DEVICES_DIR=./devices
DISPLAY_INDEX=0
SCREENSHOT_SIZE=
MAX_CONTEXT_SCREENSHOTS=5
INCLUDE_EXECUTION_FEEDBACK=false
MAX_STEPS=100
NATURAL_SCROLL=
SAVE_CONTEXT_LOG=true
CONTEXT_LOG_DIR=./logs
ENABLE_ASK_USER_FOR_SINGLE_TASK=false
```

如果订阅了 Ark Coding Plan，可使用：

```bash
API_KEY=your_api_key_here
PROVIDER=ark
BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MODEL=ark-code-latest
```

如果使用 OpenRouter，可使用：

```bash
API_KEY=your_api_key_here
PROVIDER=openrouter
BASE_URL=https://openrouter.ai/api/v1
MODEL=openai/gpt-4o-mini
PROVIDER_CONFIG_JSON={"http_referer":"https://your-app.example","title":"Computer Use Tool"}
```

其中 `PROVIDER_CONFIG_JSON` 当前会被 `openrouter` provider 用来生成推荐请求头：

- `http_referer` -> `HTTP-Referer`
- `title` -> `X-OpenRouter-Title`

如果使用 OpenAI，可使用：

```bash
API_KEY=your_api_key_here
PROVIDER=openai
BASE_URL=https://api.openai.com/v1
MODEL=gpt-4o-mini
PROVIDER_CONFIG_JSON=
MAX_TOKENS=
```

如果使用 Ollama，可使用：

```bash
API_KEY=ollama
PROVIDER=ollama
BASE_URL=http://localhost:11434/v1
MODEL=qwen2.5vl:latest
PROVIDER_CONFIG_JSON=
```

Ollama 说明：

- `MODEL` 需要你根据本地已安装模型自行配置
- 模型上下文窗口和 `MAX_TOKENS` 也需要按具体模型能力自行配置
- `THINKING_MODE=enabled/disabled` 会映射为请求体中的 `thinking={"type":"enabled"}` / `thinking={"type":"disabled"}`
- `REASONING_EFFORT` 当前不会传给 Ollama provider

## 设备插件

### `local`

默认设备插件，直接操作当前本地桌面环境。适合大多数桌面自动化场景。

### `android_adb`

通过 `adb` 控制已连接的 Android 设备。

- 运行前需要先安装 Android platform tools，并确保 `adb` 在 `PATH` 中
- 启动 Agent 前就要先连接好手机
- 当前只支持默认 adb 目标，请确保同一时刻只连接一个手机或模拟器

详细说明见 [computer_use/devices/plugins/android_adb/README.md](computer_use/devices/plugins/android_adb/README.md)。

### `vnc`

通过 `vncdotool` 控制远程 VNC 设备。

- 运行前需要先安装项目依赖中的 `vncdotool`
- 设备私有配置至少需要 `host`
- `prompt_profile` 默认是 `computer`，也可以切换成 `cellphone`

详细说明见 [computer_use/devices/plugins/vnc/README.md](computer_use/devices/plugins/vnc/README.md)。

### 插件发现规则

- 内置插件目录：`computer_use/devices/plugins/`
- 工程根目录插件目录：`./plugins/`
- 额外外部插件目录：由 `DEVICES_DIR` 指定

设备插件私有配置会通过 `DEVICE_CONFIG_JSON` 或 `--device-config-json` 原样传入插件。

## 进阶使用

### 多轮上下文与截图窗口

如果你需要了解多轮上下文如何组织、截图如何裁剪、成功反馈和失败反馈如何注入历史，请看单独文档：

- [docs/context-history.md](docs/context-history.md)

### 交互模式命令

- `/status`：查看当前生效参数
- `/display <index>`：切换目标显示器或目标设备索引，仅对支持目标切换的设备生效
- `/clear`：清空当前交互会话的多轮历史
- `/compact`：手动压缩当前旧历史文本上下文
- `/exit`：退出交互模式

### CLI 参数

```bash
python -m computer_use [指令] [选项]
```

| 参数 | 简写 | 说明 |
|------|------|------|
| `--model` | `-m` | 指定模型名称 |
| `--max-steps` | `-s` | 指定最大执行步数 |
| `--max-tokens` | - | 设置主任务模型调用的最大输出 token 数 |
| `--thinking <mode>` | `-t` | 设置思考模式，取值 `enabled` / `disabled` / `auto` |
| `--reasoning-effort <level>` | `-r` | 设置思考档位，取值 `low` / `medium` / `high` |
| `--stream` / `--no-stream` | - | 显式启用或禁用模型调用的 `stream` 参数 |
| `--coordinate-space <space>` | - | 设置坐标空间，取值 `relative` / `pixel` |
| `--coordinate-scale <value>` | - | 设置 `relative` 坐标量程，例如 `1` / `100` / `1000` |
| `--device <name>` | - | 设置设备插件名称，例如 `local`、`android_adb`、`vnc` |
| `--device-config-json <json>` | - | 设置设备插件私有 JSON 配置 |
| `--devices-dir <path>` | - | 设置外部设备插件目录 |
| `--display-index <index>` | - | 设置目标显示器编号，或其他支持 target selection 的设备目标编号 |
| `--screenshot-size <value>` | - | 设置传给模型的截图宽高，仅支持正方形 |
| `--max-context-screenshots <count>` | - | 设置多轮上下文中保留的截图数量 |
| `--include-execution-feedback` | - | 启用成功执行反馈注入 |
| `--no-execution-feedback` | - | 禁用成功执行反馈注入 |
| `--verbose` | - | 在上下文日志中记录完整 `messages`，并保存截图 |
| `--natural-scroll` | - | 显式启用自然滚动 |
| `--traditional-scroll` | - | 显式启用传统滚动 |
| `--quiet` | `-q` | 安静模式，减少输出 |
| `--version` | `-v` | 显示版本信息 |
| `--help` | `-h` | 显示帮助信息 |

## 调试与排障

### 上下文日志

如果开启 `SAVE_CONTEXT_LOG=true`，每个任务会生成 JSONL 日志，便于调试模型输入、设备状态和执行结果。

传 `--verbose` 时，还会额外：

- 记录完整 `messages`
- 将传给模型的截图保存到 `CONTEXT_LOG_DIR/screenshots/`

### 常见问题

**Q: 启动时提示缺少 API 密钥？**  
A: 请设置 `API_KEY` 环境变量或创建 `.env` 文件。

**Q: 模型调用失败？**  
A: 请检查网络连接、API 密钥和模型名称。

**Q: 截图失败？**  
A: 请检查屏幕权限设置，某些系统需要授权才能截图。

**Q: 鼠标/键盘操作无效？**  
A: 请检查是否有其他应用占用了输入控制权，或当前设备插件是否支持该动作。

**Q: 如何切换到其他兼容 OpenAI SDK 的模型服务？**  
A: 修改 `PROVIDER`、`BASE_URL`、`MODEL` 和 `API_KEY` 即可。本次重构已将 SDK 对接收敛到内部适配层，后续新增 provider profile 时无需改动 Agent 主流程。

## 面向开发者

### 项目结构

- `computer_use/agent.py`：主循环，负责截图、模型调用、动作解析和执行
- `computer_use/cli.py`：交互模式与单次任务模式入口
- `computer_use/config.py`：配置加载与持久化
- `computer_use/devices/`：设备插件体系
- `computer_use/devices/plugins/`：内置设备插件
- `computer_use/prompts.py`：桌面与手机 system prompt 模板
- `tests/`：`unittest` 测试
- `skills/`：项目内置技能定义；也可以通过 `SKILLS_DIR` 指定附加技能目录，同名技能以 `SKILLS_DIR` 为准

### 测试与开发

```bash
python check_env.py
python -m unittest discover tests
python -m unittest tests.test_action_parser
```

### 贡献

欢迎提交 Issue 和 Pull Request。请不要提交 `.env`、API key、截图文件或 JSONL 调试日志。

## 许可证

MIT License
