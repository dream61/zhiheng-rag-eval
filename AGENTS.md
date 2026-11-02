# 项目开发约定

- 本项目为知衡RAG问答质量评测平台，优先完成需求文档定义的评测闭环。
- 文档、代码注释及面向用户的说明使用简体中文。
- 技术栈固定为React18、Django5.0、Python3.12、MySQL、LangGraph、Celery、Redis、Qdrant；测试使用pytest、Playwright、Locust。
- Python包必须通过工程.venv安装，禁止全局安装；前端依赖位于frontend/node_modules。
- 模型密钥和密码仅使用环境变量，不得提交.env、数据库和令牌。
- 已发布资产不可变；实验读取冻结快照；参考答案不得输入被测生成链路。
- 执行异常、评分异常、质量失败、待复核必须分别记录；不得将mock结果描述为真实模型评测结果。
- 开发状态和验证结果及时更新docs/06-迭代与测试计划.md，不将规划功能描述为已交付。
