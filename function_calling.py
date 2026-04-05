from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.chat import ChatCompletion
import json
client = Ark()
messages = [
    {"role": "user", "content": "北京和上海今天的天气如何？"}
]
# 步骤1: 定义工具
tools = [{
  "type": "function",
  "function": {
    "name": "get_current_weather",
    "description": "获取指定地点的天气信息",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "地点的位置信息，例如北京、上海"
        },
        "unit": {
          "type": "string",
          "enum": ["摄氏度", "华氏度"],
          "description": "温度单位"
        }
      },
      "required": ["location"]
    }
  }
}]
def get_current_weather(location: str, unit="摄氏度"):
    # 实际调用天气查询 API 的逻辑
    # 此处为示例，返回模拟的天气数据
    return f"{location}今天天气晴朗，温度 25 {unit}。"
while True:
    # 步骤2: 发起模型请求，由于模型在收到工具执行结果后仍然可能有函数调用意愿，因此需要多次请求
    completion: ChatCompletion = client.chat.completions.create(
    model="doubao-seed-2-0-lite-260215",
    messages=messages,
    tools=tools
    )
    resp_msg = completion.choices[0].message
    # 展示模型中间过程的回复内容
    print(resp_msg.content)
    if completion.choices[0].finish_reason != "tool_calls":
        # 模型最终总结，没有调用工具意愿
        break
    messages.append(completion.choices[0].message.model_dump())
    tool_calls = completion.choices[0].message.tool_calls
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        if tool_name == "get_current_weather":
            # 步骤 3：调用外部工具
            args = json.loads(tool_call.function.arguments)
            tool_result = get_current_weather(**args)
            # 步骤 4：回填工具结果，并获取模型总结回复
            messages.append(
                {"role": "tool", "content": tool_result, "tool_call_id": tool_call.id}
            )
