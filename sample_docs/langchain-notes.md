# LangChain 1.x 学习笔记

## 包结构变化

LangChain 1.x 主包瘦身, 只剩 agents/chat_models/embeddings/mcp/messages/rate_limiters/tools 等少量模块。
prompts 移到了 langchain_core.prompts; 老教程里的 LLMChain、ConversationChain、AgentExecutor 在 1.x 全部废弃。
创建 Agent 用 `create_agent`, 它内部基于 LangGraph, 不再需要手动管理执行循环。

## DeepSeek 兼容层的两个大坑

第一个坑: `ChatOpenAI(max_tokens=N)` 会被 langchain_openai 自动改名成 max_completion_tokens 再发出去,
DeepSeek 不认识这个新字段就静默丢弃——不报错、不降级, 限制完全不生效。
正确写法是 `ChatOpenAI(extra_body={"max_tokens": N})`, 实测能精确截断。

第二个坑: `with_structured_output(Schema)` 默认走 json_schema 模式, DeepSeek 直接报 400。
必须写成 `with_structured_output(Schema, method="function_calling")` 才能跑通。
而 `create_agent(response_format=Schema)` 内部已经走 function_calling, 不受影响。

## 结构化输出与工具

Pydantic 模型当输出 Schema, 字段类型和描述写得越清楚模型输出越稳。
工具用 `@tool` 装饰器定义, docstring 就是给模型看的说明, 必须写清楚什么时候该调这个工具。
工具参数里放 `InjectedToolCallId` 可以注入调用编号, 模型看不到这个参数。

## 上下文管理

长对话要用中间件压上下文, SummarizationMiddleware 到阈值自动摘要历史。
注意它的 model 参数必须传模型实例, 传字符串会去 import 没装的 deepseek 专用包然后炸掉。
手写的 token 估算公式对中文普遍高估 2 到 3 倍, 阈值判断要用和计数同一个估算器,
推荐 `langchain_core.messages.utils.count_tokens_approximately`。
