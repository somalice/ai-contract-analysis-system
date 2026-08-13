"""
OCR 服务:基于 DeepSeek Vision API 的图片文字识别。
从 legacy/app.py 原样迁移(行 104-122 / 124-199 / 201-332)。
唯一变更:配置来源由模块级全局 DEEPSEEK_* 改为 current_app.config['...']。
OCR Prompt、ChatOpenAI 参数(含 legacy 中 openai_api_BASE / openai_api_base 大小写差异)、
调用流程、返回结构与 legacy 完全一致。
"""
import io
import base64
from PIL import Image
from flask import current_app
from langchain_openai import ChatOpenAI

from app.utils.text_utils import clean_text
from app.extensions.logger import logger


def encode_image_to_base64(image):
    """
    将 PIL Image 对象或图片路径转换为 base64 编码字符串
    :param image: PIL Image 对象或图片文件路径
    :return: base64 编码的字符串
    """
    # 如果传入的是路径，先打开图片
    if isinstance(image, str):
        image = Image.open(image)

    # 将图片转换为字节流
    buffered = io.BytesIO()
    # 保存为 PNG 格式到字节流
    image.save(buffered, format="PNG")
    # 获取字节内容
    img_bytes = buffered.getvalue()
    # 转换为 base64 编码并解码为字符串
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    return img_base64

def extract_text_from_image(image_path):
    """
    使用 DeepSeek API 对单张图片进行 OCR 识别
    :param image_path: 图片文件的完整路径
    :return: 识别到的文本内容字符串
    """
    print("\n" + "=" * 50)
    print("🔍 【DeepSeek OCR】正在识别图片文字")
    print("=" * 50)

    try:
        # 初始化 LangChain ChatOpenAI（用于 Vision API）
        print("【步骤1】正在初始化 DeepSeek Vision API...")
        llm = ChatOpenAI(
            model_name=current_app.config['DEEPSEEK_MODEL'],
            openai_api_key=current_app.config['DEEPSEEK_API_KEY'],
            openai_api_BASE = current_app.config['DEEPSEEK_API_BASE'],
            temperature=0.0,
            max_tokens=4000
        )
        print("✅ DeepSeek Vision API 初始化成功")

        # 将图片转换为 base64
        print("【步骤2】正在将图片转换为 base64...")
        img_base64 = encode_image_to_base64(image_path)
        print(f"   图片 base64 长度: {len(img_base64)} 字符")

        # 构建 Vision API 的 Prompt
        vision_prompt = """你是一个专业的 OCR 文字识别助手。
请仔细识别这张图片中的所有文字内容，保持原有格式和换行。

识别要求：
1. 准确识别所有文字，包括中文、英文、数字、标点符号
2. 保持原有段落结构和换行
3. 如果是合同文档，请特别注意：
   - 合同名称
   - 甲方、乙方信息
   - 金额数字
   - 日期
4. 如果图片中没有文字，请返回"（本页无文字内容）"

请直接输出识别到的文字，不要添加任何解释或其他内容。"""

        # 使用多模态功能调用（通过 content 参数）
        print("【步骤3】正在调用 DeepSeek Vision API...")
        response = llm.invoke([
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": vision_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_base64}"
                        }
                    }
                ]
            }
        ])

        # 获取识别结果
        if hasattr(response, 'content'):
            page_text = response.content
        else:
            page_text = str(response)

        print(f"✅ 图片 OCR 识别成功，识别到 {len(page_text)} 字符")
        return page_text

    except Exception as e:
        print(f"❌ 图片 OCR 识别失败: {str(e)}")
        logger.exception('OCR 处理异常')
        return ""

def extract_text_using_deepseek_ocr(file_path, file_type):
    """
    使用 DeepSeek API 进行 OCR 识别
    只对图片文件进行 OCR 识别，不处理 PDF 文件

    工作流程：
    1. 读取图片文件（仅支持 PNG/JPG/JPEG）
    2. 图片 → Base64 编码
    3. Base64 图片 → DeepSeek Vision API → 文本

    :param file_path: 文件的完整路径
    :param file_type: 文件类型 ('pdf' 或 'image')
    :return: 包含 text、pages、error 字段的字典
    """
    # 检查文件类型，只处理图片文件
    if file_type != 'image':
        print(f"❌ OCR 只支持图片文件，当前文件类型: {file_type}")
        return {
            "text": "",
            "pages": 0,
            "error": "OCR 功能仅支持图片文件（PNG/JPG/JPEG），PDF 文件请使用 pdfplumber 提取文本"
        }

    print("\n" + "=" * 50)
    print("🔍 【DeepSeek OCR】开始图片 OCR 文字识别")
    print("=" * 50)

    # 步骤1：读取图片
    print("\n【步骤1】正在读取图片...")
    try:
        # 直接读取图片文件
        image = Image.open(file_path)
        images = [image]
        print(f"✅ 图片读取成功，共 {len(images)} 张")
    except Exception as e:
        print(f"❌ 图片读取失败: {str(e)}")
        logger.exception('OCR 处理异常')
        return {
            "text": "",
            "pages": 0,
            "error": f"图片读取失败: {str(e)}"
        }

    # 步骤2：逐张图片 OCR 识别
    all_text = []
    total_pages = len(images)

    print(f"\n【步骤2】开始 OCR 识别（共 {total_pages} 张图片）...")

    for i, image in enumerate(images):
        page_num = i + 1
        print(f"\n   --- 第 {page_num}/{total_pages} 张 ---")

        try:
            # 将图片转换为 base64
            img_base64 = encode_image_to_base64(image)
            print(f"   第 {page_num} 张：图片已转换为 base64，长度: {len(img_base64)} 字符")

            # 初始化 LangChain ChatOpenAI（用于 Vision API）
            llm = ChatOpenAI(
                model_name=current_app.config['DEEPSEEK_MODEL'],
                openai_api_key=current_app.config['DEEPSEEK_API_KEY'],
                openai_api_base=current_app.config['DEEPSEEK_API_BASE'],
                temperature=0.0,
                max_tokens=4000
            )

            # 构建 Vision API 的 Prompt
            vision_prompt = """你是一个专业的 OCR 文字识别助手。
请仔细识别这张图片中的所有文字内容，保持原有格式和换行。

识别要求：
1. 准确识别所有文字，包括中文、英文、数字、标点符号
2. 保持原有段落结构和换行
3. 如果是合同文档，请特别注意：
   - 合同名称
   - 甲方、乙方信息
   - 金额数字
   - 日期
4. 如果图片中没有文字，请返回"（本页无文字内容）"

请直接输出识别到的文字，不要添加任何解释或其他内容。"""

            # 使用多模态功能调用（通过 content 参数）
            response = llm.invoke([
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": vision_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ])

            # 获取识别结果
            if hasattr(response, 'content'):
                page_text = response.content
            else:
                page_text = str(response)

            print(f"   第 {page_num} 张：识别到 {len(page_text)} 字符")
            all_text.append(page_text)

        except Exception as e:
            print(f"   ❌ 第 {page_num} 张 OCR 识别失败: {str(e)}")
            logger.exception('OCR 处理异常')
            all_text.append(f"\n[第 {page_num} 张识别失败]\n")

    # 步骤3：合并所有图片的识别结果
    print("\n【步骤3】正在合并识别结果...")
    final_text = '\n\n'.join(all_text)
    final_text = clean_text(final_text)

    print(f"\n{'=' * 50}")
    print(f"🔍 【DeepSeek OCR】OCR 识别完成！")
    print(f"   总图片数: {total_pages}")
    print(f"   最终文本长度: {len(final_text)} 字符")
    print(f"{'=' * 50}\n")

    return {
        "text": final_text,
        "pages": total_pages,
        "error": None
    }
