# Computer Use Tool

基于火山方舟模型的本地 GUI 自动化工具。

## 功能特性

- 🤖 **多轮自动执行** - 自动循环执行直到任务完成
- 🖱️ **丰富操作支持** - 点击、输入、滚动、拖拽、热键等
- 📸 **截图保存** - 支持开关配置，便于调试
- ⚙️ **灵活配置** - 支持环境变量和配置文件
- 💻 **CLI 交互** - 支持交互式和单次任务模式

## 环境要求

- **操作系统**: macOS / Windows / Linux
- **Python**: 3.8 或更高版本
- **网络**: 可访问火山方舟 API

## 快速开始

### 1. 创建虚拟环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
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
| 最大步数 | `MAX_STEPS` | `20` | 最大执行步数 |
| 保存截图 | `SAVE_SCREENSHOT` | `true` | 是否保存截图 |
| 截图目录 | `SCREENSHOT_DIR` | `./screenshots` | 截图保存目录 |

### `.env` 文件示例

```bash
# 必需配置
ARK_API_KEY=your_api_key_here

# 可选配置
ARK_MODEL=doubao-seed-1-6-vision-250815
ARK_BASE_URL=http://ark.cn-beijing.volces.com/api/v3
TEMPERATURE=0.0
MAX_STEPS=20

# 截图配置
SAVE_SCREENSHOT=true
SCREENSHOT_DIR=./screenshots
```

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
| `--no-screenshot` | - | 禁用截图保存 |
| `--screenshot-dir` | - | 指定截图保存目录 |
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

# 指定最大步数
python -m computer_use "搜索 Python 教程" --max-steps 10

# 禁用截图保存
python -m computer_use "打开计算器" --no-screenshot

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
