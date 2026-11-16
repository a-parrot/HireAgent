# DeepSeek 环境配置

在 backend/.env 添加以下参数，保存并重启后端即可切换：

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=填写你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_MAX_TOKENS=8192
DEEPSEEK_TIMEOUT=300
LLM_ENABLE_THINKING=false
```

- 必填：DEEPSEEK_API_KEY，请直接在本机 .env 填写，不提交到 Git。
- 服务地址与模型名：默认对应官方兼容接口；如果通过第三方平台部署 DeepSeek，需要填写该平台提供的地址、模型标识和密钥。
- 可选：输出预算、超时、思考开关。新模型使用 thinking.type，默认关闭思考，适合结构化筛选。
- 原有云模型及 llama 配置可保留。切换提供方时使用独立密钥，不会混用其他模型凭证。

验证连通性：从 backend 运行 `.venv/Scripts/python.exe test/test_llm_client.py`，仅发送测试问题，不读取真实简历。历史评估不自动更新，需要重新发起评估。

官方说明：https://api-docs.deepseek.com/quick_start/agent_integrations/
