"""
DeepSeek LLM 客户端封装(Sprint 5 - v0.7.0 / v0.7.1 增强)

职责:
- 封装 DeepSeek Chat API 调用(复用 rag_service 的 ChatOpenAI 调用模式)
- 供 ContractReviewAgent 在 ReAct 循环中调用

设计:
- 复用 current_app.config 的 DEEPSEEK_* 配置(与 deepseek_service / rag_service 一致)
- temperature=0.0(决策需要稳定,非创造性)
- 失败返回 (None, error, error_type),由 Agent 决策降级

v0.7.1 增强(Sprint 5 Final):
- 新增 timeout 配置(从 .env LLM_TIMEOUT 读取,默认 30s)
- 新增错误分类:timeout / rate_limit / server_error / network / auth / framework / unknown
- 返回三元组 (text, error, error_type) 供 Agent 精准降级
- max_tokens 从 config.LLM_MAX_TOKENS 读取

Sprint 8 企业级增强(v1.0.0):
- 新增 contextvars 累计每次 Agent.run() 内的总 token 用量(input_tokens/output_tokens/total_tokens)
- 提供 reset_run_usage() / get_run_usage() 接口,供 Service 层在 agent.run() 前后调用
- 注意:call_deepseek() 返回签名保持不变,完全向前兼容
"""
import contextvars
import time
from typing import Optional, Tuple

from flask import current_app

from app.extensions.logger import logger


# ---------- Sprint 8:Agent 单次运行 token 累计 ----------
# contextvars:Flask 多请求线程隔离;一个请求 / 一次 agent.run 调用形成独立上下文
_run_usage_var = contextvars.ContextVar(
    'llm_client_run_usage',
    default=None,  # None 表示尚未开始累计
)


def _start_run_usage_if_missing():
    """若上下文未初始化,初始化为 0 结构并返回引用"""
    cur = _run_usage_var.get()
    if cur is None:
        cur = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'call_count': 0}
        _run_usage_var.set(cur)
    return cur


def reset_run_usage():
    """
    重置当前上下文的 token 累计。
    Service 层每次 agent.run() 前调用,避免上下文复用导致旧数据残留。
    """
    _run_usage_var.set({
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'call_count': 0,
    })


def get_run_usage():
    """
    获取当前上下文累计的 token 用量。

    :return: dict {input_tokens, output_tokens, total_tokens, call_count}
        未 reset 时返回全 0 结构。
    """
    cur = _run_usage_var.get()
    if cur is None:
        return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'call_count': 0}
    return dict(cur)


def _accumulate_usage(usage_metadata):
    """
    从 LangChain ChatModel 返回的 usage_metadata 中提取 token 并累计。

    usage_metadata 结构:
    {'input_tokens': 120, 'output_tokens': 50, 'total_tokens': 170,
     'input_token_details': {...}, 'output_token_details': {...}}
    (不同 langchain-core 版本可能字段略有差异,此处做防御)
    """
    if not isinstance(usage_metadata, dict):
        return
    try:
        cur = _start_run_usage_if_missing()
        i = int(usage_metadata.get('input_tokens') or 0)
        o = int(usage_metadata.get('output_tokens') or 0)
        t = int(usage_metadata.get('total_tokens') or 0) or (i + o)
        cur['input_tokens'] += i
        cur['output_tokens'] += o
        cur['total_tokens'] += t
        cur['call_count'] += 1
    except Exception as e:
        # 累计失败不影响主流程
        logger.warning('[Agent:llm_client] token 累计异常: %s', e)


# ---------- LLM 错误类型枚举 ----------
ERROR_TYPE_TIMEOUT = 'timeout'
ERROR_TYPE_RATE_LIMIT = 'rate_limit'
ERROR_TYPE_SERVER_ERROR = 'server_error'
ERROR_TYPE_NETWORK = 'network'
ERROR_TYPE_AUTH = 'auth'
ERROR_TYPE_FRAMEWORK = 'framework'
ERROR_TYPE_UNKNOWN = 'unknown'

# Sprint 8.6: 可重试错误类型(transport 层抖动,重试有意义)
# auth(配置错误) / framework(依赖缺失) / unknown(未知,重试无意义) 不重试
_RETRYABLE_ERRORS = {
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_RATE_LIMIT,
    ERROR_TYPE_SERVER_ERROR,
    ERROR_TYPE_NETWORK,
}


def _classify_error(exc: Exception) -> str:
    """
    分类 LLM 调用异常

    :param exc: 捕获的异常
    :return: 错误类型字符串
    """
    err_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # 超时
    if 'timeout' in err_str or 'timed out' in err_str or 'timeout' in exc_type:
        return ERROR_TYPE_TIMEOUT

    # 429 限流
    if '429' in err_str or 'rate' in err_str or 'quota' in err_str:
        return ERROR_TYPE_RATE_LIMIT

    # 5xx 服务端错误
    if any(code in err_str for code in ('500', '502', '503', '504', 'internal server error')):
        return ERROR_TYPE_SERVER_ERROR

    # 401 / 403 认证失败
    if '401' in err_str or '403' in err_str or 'auth' in err_str or 'api key' in err_str or 'unauthorized' in err_str:
        return ERROR_TYPE_AUTH

    # 网络异常
    if any(kw in err_str for kw in ('connection', 'network', 'resolve', 'reachable', 'refused', 'dns')):
        return ERROR_TYPE_NETWORK

    # 框架异常
    if 'import' in err_str or 'module' in err_str or 'attribute' in err_str:
        return ERROR_TYPE_FRAMEWORK

    return ERROR_TYPE_UNKNOWN


def _error_message(error_type: str) -> str:
    """根据错误类型生成用户友好的错误信息"""
    messages = {
        ERROR_TYPE_TIMEOUT: 'LLM 调用超时,已自动降级规则引擎',
        ERROR_TYPE_RATE_LIMIT: 'LLM 请求被限流(429),已自动降级规则引擎',
        ERROR_TYPE_SERVER_ERROR: 'LLM 服务端错误(5xx),已自动降级规则引擎',
        ERROR_TYPE_NETWORK: 'LLM 网络异常,无法连接 DeepSeek,已自动降级规则引擎',
        ERROR_TYPE_AUTH: 'LLM 认证失败(API Key 无效),已自动降级规则引擎',
        ERROR_TYPE_FRAMEWORK: 'LLM 框架异常(langchain 未安装或版本不兼容)',
        ERROR_TYPE_UNKNOWN: 'LLM 调用失败(未知原因),已自动降级规则引擎',
    }
    return messages.get(error_type, messages[ERROR_TYPE_UNKNOWN])


def call_deepseek(system_prompt: str, human_prompt: str,
                  max_tokens: Optional[int] = None
                  ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    调用 DeepSeek 生成回答

    :param system_prompt: System Prompt
    :param human_prompt: Human Prompt(可含 {占位符},调用前需已填充)
    :param max_tokens: 最大输出 token(None 时从 config 读取)
    :return: (response_text, error, error_type)
        - 成功:(text, None, None)
        - 失败:(None, error_message, error_type)
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return None, 'DEEPSEEK_API_KEY 未配置,无法调用 LLM', ERROR_TYPE_AUTH

    # 从 config 读取超时与 max_tokens(v0.7.1 新增;Sprint 8.8 拆 connect/read)
    # 兼容:LLM_TIMEOUT 存在时作为 read 兜底(旧 .env 无需改动)
    _llm_read = current_app.config.get('LLM_READ_TIMEOUT', current_app.config.get('LLM_TIMEOUT', 30))
    _llm_connect = current_app.config.get('LLM_CONNECT_TIMEOUT', 5)
    if max_tokens is None:
        max_tokens = current_app.config.get('LLM_MAX_TOKENS', 2000)

    try:
        import httpx
        timeout = httpx.Timeout(timeout=_llm_read, connect=_llm_connect)
    except ImportError:
        timeout = _llm_read  # httpx 缺失时退化为单值超时

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
    except ImportError:
        logger.exception('[Agent:llm_client] langchain 未安装')
        return None, 'LLM 框架未安装', ERROR_TYPE_FRAMEWORK

    try:
        llm = ChatOpenAI(
            model_name=current_app.config['DEEPSEEK_MODEL'],
            openai_api_key=api_key,
            openai_api_base=current_app.config['DEEPSEEK_API_BASE'],
            temperature=0.0,   # 决策稳定,非创造性
            max_tokens=max_tokens,
            timeout=timeout,   # v0.7.1: 超时控制(Sprint 8.8: connect/read 分离)
            max_retries=current_app.config.get('LLM_MAX_RETRIES', 1),  # Sprint 8.8: 重试封顶
        )
        # v0.7.1: 使用直接 Message 而非 ChatPromptTemplate
        # 原因:prompt 已由 _build_human_prompt() 用 .format() 预填充,
        #       ChatPromptTemplate 会二次解析 {}/{} 导致 JSON 示例中的
        #       {"action":"call_tool"} 被误认为模板变量(KeyError)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]
    except Exception as e:
        # ChatOpenAI 构造异常(多为配置问题,不可重试)
        error_type = _classify_error(e)
        logger.exception('[Agent:llm_client] ChatOpenAI 构造失败: type=%s', error_type)
        return None, _error_message(error_type), error_type

    # ---------- Sprint 8.6: 重试循环(transport 层抖动容错)----------
    # 仅对 timeout / rate_limit / server_error / network 重试;
    # auth / framework / unknown 立即返回由 Agent 降级。
    max_retries = current_app.config.get('LLM_MAX_RETRIES', 2)
    attempt = 0
    while True:
        attempt += 1
        try:
            response = llm.invoke(messages)
            text = response.content if hasattr(response, 'content') else str(response)
            # Sprint 8: 累计 token(有 usage_metadata 则累加上下文)
            try:
                usage = getattr(response, 'usage_metadata', None)
                if isinstance(usage, dict):
                    _accumulate_usage(usage)
            except Exception as _e:
                logger.warning('[Agent:llm_client] 读取 response.usage_metadata 失败: %s', _e)
            return text, None, None
        except Exception as e:
            error_type = _classify_error(e)
            # 不可重试 或 已超最大重试次数 → 返回错误,由 Agent 决策降级
            if attempt > max_retries or error_type not in _RETRYABLE_ERRORS:
                error_msg = _error_message(error_type)
                logger.exception('[Agent:llm_client] DeepSeek 调用失败(放弃重试): type=%s attempt=%s/%s',
                                 error_type, attempt, max_retries)
                return None, error_msg, error_type
            # 指数退避:1s, 2s, 4s 封顶
            backoff = min(2 ** (attempt - 1), 4)
            logger.warning('[Agent:llm_client] 重试 %s/%s type=%s backoff=%ss',
                           attempt, max_retries, error_type, backoff)
            time.sleep(backoff)
