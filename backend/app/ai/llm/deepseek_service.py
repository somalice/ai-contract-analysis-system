"""
LLM 服务:基于 DeepSeek Chat API 的合同字段提取。
从 legacy/app.py 原样迁移(行 368-524)。
唯一变更:配置来源由模块级全局 DEEPSEEK_* 改为 current_app.config['...']。
字段提取 Prompt、ChatPromptTemplate、Chain(prompt | llm)、JSON 解析、错误返回结构与 legacy 完全一致。
"""
import json
from flask import current_app
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.extensions.logger import logger


def extract_contract_fields(text):
    """
    使用 LangChain + DeepSeek API 从合同文本中提取关键字段
    :param text: 合同文本内容
    :return: 提取的字段字典，包含合同名称、甲方、乙方、合同金额、签署日期
    """
    # 记录开始时间，用于调试
    print("\n" + "=" * 50)
    print("【AI分析】开始合同字段提取")
    print("=" * 50)

    # 步骤1：初始化 LangChain 模型
    try:
        print("【步骤1】正在初始化 LangChain ChatOpenAI 模型...")
        llm = ChatOpenAI(
            model_name=current_app.config['DEEPSEEK_MODEL'],      # 使用 DeepSeek 模型
            openai_api_key=current_app.config['DEEPSEEK_API_KEY'], # 设置 API Key
            openai_api_base=current_app.config['DEEPSEEK_API_BASE'], # 设置 API 地址
            temperature=0.0,                # 温度设置为 0，确保输出稳定
            max_tokens=500                  # 限制输出长度
        )
        print("✅ LangChain 模型初始化成功")
        print(f"   模型名称: {current_app.config['DEEPSEEK_MODEL']}")
        print(f"   API 地址: {current_app.config['DEEPSEEK_API_BASE']}")
    except Exception as e:
        print("❌ LangChain 模型初始化失败")
        print(f"   错误信息: {str(e)}")
        logger.exception('DeepSeek 调用异常')  # 打印完整的错误堆栈
        return {
            "contract_name": "",
            "party_a": "",
            "party_b": "",
            "amount": "",
            "signing_date": "",
            "error": f"LangChain 初始化失败: {str(e)}"
        }

    # 步骤2：设计 Prompt
    try:
        print("\n【步骤2】正在构建 Prompt...")
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业的合同分析助手。请从合同文本中提取以下关键字段：

需要提取的字段：
1. 合同名称 - 合同的正式名称
2. 甲方 - 合同的甲方全称
3. 乙方 - 合同的乙方全称
4. 合同金额 - 合同涉及的总金额（包含货币单位）
5. 签署日期 - 合同签署的日期

输出格式要求：
请以 JSON 格式输出，字段名分别为：contract_name, party_a, party_b, amount, signing_date
如果某个字段无法找到，请返回空字符串 ""

示例输出：
{{
    "contract_name": "软件开发合同",
    "party_a": "北京科技有限公司",
    "party_b": "上海软件技术有限公司",
    "amount": "人民币壹佰万元整（¥1,000,000.00）",
    "signing_date": "2024年1月15日"
}}
"""),
            ("human", "请分析以下合同文本并提取关键字段：\n\n{contract_text}")
        ])
        print("✅ Prompt 构建成功")
    except Exception as e:
        print("❌ Prompt 构建失败")
        print(f"   错误信息: {str(e)}")
        logger.exception('DeepSeek 调用异常')
        return {
            "contract_name": "",
            "party_a": "",
            "party_b": "",
            "amount": "",
            "signing_date": "",
            "error": f"Prompt 构建失败: {str(e)}"
        }

    # 步骤3：创建 Chain
    try:
        print("\n【步骤3】正在创建 LangChain Chain...")
        chain = prompt | llm
        print("✅ Chain 创建成功")
    except Exception as e:
        print("❌ Chain 创建失败")
        print(f"   错误信息: {str(e)}")
        logger.exception('DeepSeek 调用异常')
        return {
            "contract_name": "",
            "party_a": "",
            "party_b": "",
            "amount": "",
            "signing_date": "",
            "error": f"Chain 创建失败: {str(e)}"
        }

    # 步骤4：调用 DeepSeek API
    response_content = None
    try:
        print("\n【步骤4】正在调用 DeepSeek API...")
        print(f"   输入文本长度: {len(text)} 字符")
        print(f"   API Key 前 10 位: {current_app.config['DEEPSEEK_API_KEY'][:10]}...")

        # 调用链执行提取任务
        response = chain.invoke({"contract_text": text})

        print("✅ DeepSeek API 调用成功")
        print(f"   响应类型: {type(response)}")

        # 获取响应内容
        if hasattr(response, 'content'):
            response_content = response.content
            print(f"   响应内容长度: {len(response_content)} 字符")
            print(f"   响应内容预览: {response_content[:100]}...")
        else:
            print(f"   响应对象: {response}")
            response_content = str(response)

    except Exception as e:
        print("❌ DeepSeek API 调用失败")
        print(f"   错误信息: {str(e)}")
        logger.exception('DeepSeek 调用异常')
        return {
            "contract_name": "",
            "party_a": "",
            "party_b": "",
            "amount": "",
            "signing_date": "",
            "error": f"DeepSeek API 调用失败: {str(e)}"
        }

    # 步骤5：解析 JSON 结果
    try:
        print("\n【步骤5】正在解析 JSON 结果...")
        result = json.loads(response_content)
        print("✅ JSON 解析成功")
        print(f"   解析结果: {result}")
    except Exception as e:
        print("❌ JSON 解析失败")
        print(f"   错误信息: {str(e)}")
        print(f"   原始响应内容: {response_content}")
        logger.exception('DeepSeek 调用异常')
        return {
            "contract_name": "",
            "party_a": "",
            "party_b": "",
            "amount": "",
            "signing_date": "",
            "error": f"JSON 解析失败: {str(e)} | 原始响应: {response_content}"
        }

    print("\n" + "=" * 50)
    print("【AI分析】合同字段提取完成")
    print("=" * 50 + "\n")

    return result
