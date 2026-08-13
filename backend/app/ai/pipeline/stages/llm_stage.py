"""
LLM Stage(Sprint 3 - v0.5.0)

职责:
- 调用 DeepSeek Chat API,从合同文本提取 8 个结构化字段
- 输出严格 JSON,缺失字段返回 null(禁止编造)
- 每字段含 value / confidence / source

设计要点(遵循用户规则 §11 Prompt Engineering Rules):
- Prompt 从 ai/pipeline/prompts/contract_extract_v1.md 加载,不硬编码
- 输出 JSON Schema 强约束(LangChain with_structured_output 不可用时手动解析 + 容错)
- 失败重试一次;仍失败则字段全 null(Task 标记 failed)

触发条件:ctx.chunks 非空
失败情况:
- API Key 未配置 → failed
- API 调用异常 → failed
- JSON 解析失败(重试后仍失败)→ failed
"""
import os
import json
from flask import current_app
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.extensions.logger import logger


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts', 'contract_extract_v1.md'
)

# ---------- 8 个字段名(与 ContractField.FIELD_NAMES 一致) ----------
_EXPECTED_FIELDS = (
    'contract_no', 'contract_name', 'party_a', 'party_b',
    'amount', 'sign_date', 'payment_method', 'valid_period',
)

# ---------- 重试次数 ----------
_MAX_RETRIES = 1


class LlmStage(BaseStage):
    """LLM 结构化字段提取 Stage"""

    @property
    def name(self) -> str:
        return 'llm'

    def should_run(self, ctx: PipelineContext) -> bool:
        return bool(ctx.chunks)

    def _execute(self, ctx: PipelineContext) -> StageResult:
        # ---------- 1. 校验 API Key ----------
        api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
        if not api_key:
            logger.error('[Pipeline:llm] DEEPSEEK_API_KEY 未配置')
            return StageResult(StageResult.FAILED,
                               error='DEEPSEEK_API_KEY 未配置,无法调用 LLM')

        # ---------- 2. 准备输入文本 ----------
        # 将所有 Chunk 合并(已由 chunk_stage 截断到安全长度)
        contract_text = '\n\n'.join(ctx.chunks)
        logger.info('[Pipeline:llm] 开始 LLM 字段提取: 输入长度=%s', len(contract_text))

        # ---------- 3. 加载 Prompt ----------
        system_prompt, human_prompt = self._load_prompt()

        # ---------- 4. 初始化 LLM ----------
        try:
            llm = ChatOpenAI(
                model_name=current_app.config['DEEPSEEK_MODEL'],
                openai_api_key=api_key,
                openai_api_base=current_app.config['DEEPSEEK_API_BASE'],
                temperature=0.0,  # 温度 0,确保输出稳定
                max_tokens=2000,  # 8 字段 JSON 约需 1K token
            )
        except Exception as e:
            logger.exception('[Pipeline:llm] LLM 初始化失败')
            return StageResult(StageResult.FAILED, error=f'LLM 初始化失败: {e}')

        # ---------- 5. 调用 + 重试 ----------
        last_error = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._invoke_llm(llm, system_prompt, human_prompt, contract_text)
                fields = self._parse_response(response)

                # 校验字段完整性(8 个字段必须都有,缺失的补 null)
                fields = self._ensure_field_completeness(fields)

                ctx.fields = fields

                # 统计
                found_count = sum(1 for f in fields if f.get('value'))
                avg_conf = (
                    sum(f.get('confidence', 0.0) for f in fields) / len(fields)
                    if fields else 0.0
                )

                metadata = {
                    'attempt': attempt + 1,
                    'field_count': len(fields),
                    'found_count': found_count,
                    'null_count': len(fields) - found_count,
                    'avg_confidence': round(avg_conf, 4),
                    'response_length': len(response) if response else 0,
                }
                logger.info('[Pipeline:llm] LLM 提取完成: 找到 %s/%s 字段, 平均置信度=%.2f',
                            found_count, len(fields), avg_conf)
                return StageResult(StageResult.SUCCESS, metadata=metadata)

            except json.JSONDecodeError as e:
                last_error = f'JSON 解析失败: {e}'
                logger.warning('[Pipeline:llm] 第 %s 次尝试 JSON 解析失败: %s',
                               attempt + 1, e)
            except Exception as e:
                last_error = f'LLM 调用失败: {e}'
                logger.warning('[Pipeline:llm] 第 %s 次尝试失败: %s', attempt + 1, e)

        # 重试耗尽
        logger.error('[Pipeline:llm] LLM 提取最终失败: %s', last_error)
        return StageResult(StageResult.FAILED, error=last_error or 'LLM 提取失败')

    # ---------- 辅助方法 ----------
    @staticmethod
    def _load_prompt():
        """
        Sprint 8 新增:DB active 模板优先(contract_extract),失败回退原文件解析逻辑。
        :return: (system_prompt, human_prompt_template)
        """
        # Sprint 8: DB active Prompt 优先
        try:
            from app.services import prompt_service
            tpl = prompt_service.get_active_template('contract_extract')
            if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
                return tpl['system_prompt'], tpl['human_prompt']
        except Exception as _e:
            logger.warning('[Pipeline:llm] PromptTemplate DB 查询失败,回退原 .md 文件: %s', _e)

        # ---------- Sprint 0~7 原逻辑(100% 保留,作为 fallback)----------
        try:
            with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as e:
            logger.exception('[Pipeline:llm] Prompt 文件加载失败: %s', _PROMPT_FILE)
            # 兜底:极简 Prompt(避免 Prompt 文件缺失导致完全无法运行)
            return (
                '你是合同分析助手。从合同文本提取 8 个字段(contract_no, contract_name, '
                'party_a, party_b, amount, sign_date, payment_method, valid_period),'
                '输出严格 JSON:{"fields":[{"name","value","confidence","source"}]},'
                '缺失字段 value=null, confidence=0.0, source=null,禁止编造。',
                '请分析以下合同文本:\n\n{contract_text}'
            )

        # 解析 Markdown:提取 "## System Prompt" 和 "## Human Prompt" 两节
        # System Prompt:从 "## System Prompt" 到 "## 输出格式要求"
        # Human Prompt:"## Human Prompt" 之后的内容,含 {contract_text} 占位符
        system_prompt = ''
        human_prompt = '{contract_text}'

        lines = content.split('\n')
        current_section = None
        system_lines = []
        human_lines = []

        for line in lines:
            if line.strip() == '## System Prompt':
                current_section = 'system'
                continue
            if line.strip() == '## Human Prompt':
                current_section = 'human'
                continue
            if line.strip().startswith('## ') and current_section:
                # 进入下一节,结束当前节收集
                current_section = None
                continue
            if current_section == 'system':
                system_lines.append(line)
            elif current_section == 'human':
                human_lines.append(line)

        system_prompt = '\n'.join(system_lines).strip()
        human_prompt = '\n'.join(human_lines).strip()

        if not system_prompt:
            logger.warning('[Pipeline:llm] 未能从 Prompt 文件解析出 System Prompt,使用兜底')
            system_prompt = '你是合同分析助手,输出严格 JSON。'

        return system_prompt, human_prompt

    @staticmethod
    def _invoke_llm(llm, system_prompt, human_prompt, contract_text):
        """
        调用 LLM
        :return: response.content 字符串

        注意:system_prompt 中含 JSON 输出格式示例(带 { } 字符),
        需转义为 {{ }} 避免 ChatPromptTemplate 将其误判为模板变量。
        human_prompt 仅含 {contract_text} 占位符,不转义。
        """
        # 转义 system_prompt 中的 { } 为 {{ }},避免 JSON 示例被当模板变量
        escaped_system = system_prompt.replace('{', '{{').replace('}', '}}')
        prompt = ChatPromptTemplate.from_messages([
            ('system', escaped_system),
            ('human', human_prompt),
        ])
        chain = prompt | llm
        response = chain.invoke({'contract_text': contract_text})

        if hasattr(response, 'content'):
            return response.content
        return str(response)

    @staticmethod
    def _parse_response(response_text):
        """
        解析 LLM 返回的 JSON
        :return: list[dict] fields
        :raises: json.JSONDecodeError
        """
        if not response_text:
            raise json.JSONDecodeError('空响应', '', 0)

        # 清理可能的 Markdown 代码块包裹
        text = response_text.strip()
        if text.startswith('```'):
            # 去掉 ```json 或 ``` 开头和结尾的 ```
            lines = text.split('\n')
            # 移除首行(可能是 ```json)
            if lines[0].strip().startswith('```'):
                lines = lines[1:]
            # 移除末尾的 ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines).strip()

        # 尝试定位最外层 { ... }
        # (模型偶尔会在 JSON 前后加一句解释,这里容错)
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise json.JSONDecodeError('未找到 JSON 边界', text, 0)

        json_str = text[start:end + 1]
        data = json.loads(json_str)

        # 预期结构:{"fields": [{"name","value","confidence","source"}, ...]}
        fields = data.get('fields', []) if isinstance(data, dict) else []
        if not isinstance(fields, list):
            fields = []

        # 规范化每个字段
        normalized = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            name = f.get('name')
            if not name:
                continue
            normalized.append({
                'name': str(name),
                'value': f.get('value'),  # 允许 None
                'confidence': float(f.get('confidence') or 0.0),
                'source': f.get('source'),
            })

        return normalized

    @staticmethod
    def _ensure_field_completeness(fields):
        """
        确保返回的 fields 包含全部 8 个字段(缺失补 null)
        顺序与 _EXPECTED_FIELDS 一致
        """
        field_map = {f['name']: f for f in fields}

        result = []
        for name in _EXPECTED_FIELDS:
            if name in field_map:
                result.append(field_map[name])
            else:
                # 缺失字段补 null
                result.append({
                    'name': name,
                    'value': None,
                    'confidence': 0.0,
                    'source': None,
                })
        return result
