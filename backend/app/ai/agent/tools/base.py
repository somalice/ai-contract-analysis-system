"""
Tool 抽象基类(Sprint 5 - v0.7.0)

职责:
- 定义 Tool 统一契约:name / description / args_schema / run
- 每个 Tool 职责单一(字段查询 / RAG 检索 / 规则检查)

设计原则(遵循 user_rules §9 Tool Design Rules):
- Stateless:Tool 不持有跨调用状态
- Independent:Tool 不直接调用其他 Tool
- Reusable:Tool 可独立实例化测试
- Testable:每个 Tool 可单独传入 AgentContext 测试

借鉴 Sprint 3 BaseStage 模式(Stage 与 Tool 均为单一职责可替换组件)。
"""
from abc import ABC, abstractmethod
from typing import Any

from app.ai.agent.context import AgentContext


class BaseTool(ABC):
    """Tool 抽象基类(LLM 据此选择调用哪个 Tool)"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool 名称(LLM 据此选择,需唯一)"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool 描述(写进 Prompt,供 LLM 理解工具用途)"""

    @property
    def args_schema(self) -> dict:
        """
        参数 schema(写进 Prompt,供 LLM 构造 args)
        :return: dict,描述参数结构,如 {'query': '检索关键词(必填)'}
        默认无参数,子类按需覆盖
        """
        return {}

    @abstractmethod
    def run(self, args: dict, ctx: AgentContext) -> dict:
        """
        执行 Tool(子类实现)
        :param args: LLM 传入的参数(可能为空 dict)
        :param ctx: AgentContext(提供 contract_id / fields / document_text 等)
        :return: 结构化 dict(将序列化为 JSON 喂给 LLM)
                 必须包含足够信息供 LLM 决策,避免过大(控制 token)
        """

    def to_prompt_dict(self) -> dict:
        """转为 Prompt 描述(LLM 据此理解工具)"""
        return {
            'name': self.name,
            'description': self.description,
            'args_schema': self.args_schema,
        }

    def safe_run(self, args: dict, ctx: AgentContext) -> dict:
        """
        安全执行入口(由 Agent 调用)
        - 参数容错:args 非 dict 时置为 {}
        - 异常兜底:Tool 内部未捕获异常时返回 error dict,不炸 Agent 循环
        - 日志增强(v0.7.1):记录 Tool 开始 / 结束 / 耗时
        :return: dict,异常时含 {'error': '...'}
        """
        from datetime import datetime
        from app.extensions.logger import logger

        if not isinstance(args, dict):
            args = {}

        start_ts = datetime.utcnow()
        logger.info('[Tool:%s] 开始执行: args=%s', self.name,
                    str(args)[:100] if args else '(无参数)')

        try:
            result = self.run(args, ctx)
            duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
            if not isinstance(result, dict):
                logger.warning('[Tool:%s] 返回非 dict: %s (%dms)',
                               self.name, type(result), duration_ms)
                return {'error': f'Tool {self.name} 返回非 dict: {type(result)}'}
            # 附加耗时信息(v0.7.1,供 trace 使用)
            logger.info('[Tool:%s] 执行完成: %dms, status=success',
                        self.name, duration_ms)
            return result
        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
            logger.exception('[Tool:%s] 执行异常: %dms, error=%s',
                             self.name, duration_ms, e)
            return {'error': f'Tool {self.name} 执行失败: {e}'}
