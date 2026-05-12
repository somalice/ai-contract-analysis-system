# 导入 Flask 框架核心模块
from flask import Flask, render_template, request, flash
# 导入操作系统相关功能，用于文件路径处理
import os
import json
import base64
import io
# 导入 traceback 模块，用于打印详细的错误堆栈信息
import traceback
# 导入安全文件名处理函数，防止路径遍历攻击
from werkzeug.utils import secure_filename
# 导入 pdfplumber 库，用于提取 PDF 文件中的文本内容
import pdfplumber
# 导入 PIL 用于处理图片
from PIL import Image
# 导入 dotenv 用于加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================================
# 导入 LangChain 相关模块
# ==========================================================
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# 初始化 Flask 应用实例
app = Flask(__name__)
# 设置会话密钥，用于加密会话数据和 flash 消息
app.secret_key = 'supersecretkey'
# 配置文件上传目录，上传的文件将保存在此目录下
app.config['UPLOAD_FOLDER'] = 'uploads'
# 配置允许上传的文件扩展名（PDF + 图片格式）
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'png', 'jpg', 'jpeg'}
# 配置最大上传文件大小（10MB）
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# DeepSeek API 配置
# 从环境变量读取 API Key（请在 .env 文件中配置）
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
# DeepSeek API 基础 URL
DEEPSEEK_API_BASE = 'https://api.deepseek.com/v1'
# 使用的模型名称
DEEPSEEK_MODEL = 'deepseek-chat'

def allowed_file(filename):
    """
    检查文件名是否符合允许的扩展名要求
    :param filename: 上传的文件名
    :return: 如果扩展名在允许列表中返回 True，否则返回 False
    """
    # 检查文件名中是否包含点号，并且扩展名（不区分大小写）在允许列表中
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_file_type(filename):
    """
    获取文件类型（PDF 或图片）
    :param filename: 上传的文件名
    :return: 'pdf' 或 'image'
    """
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext == 'pdf':
        return 'pdf'
    else:
        return 'image'

def clean_text(text):
    """
    清理提取的文本，提高可读性
    :param text: 原始提取的文本
    :return: 清理后的文本
    """
    if not text:
        return ""

    # 将文本按行分割
    lines = text.split('\n')

    # 处理每一行
    cleaned_lines = []
    for line in lines:
        # 1. 去除每行首尾的空白字符
        line = line.strip()

        # 2. 去除行内多余的连续空格（多个空格变成一个空格）
        line = ' '.join(line.split())

        # 3. 只保留非空行（但保留段落分隔的空行）
        if line:
            cleaned_lines.append(line)

    # 4. 将处理后的行重新组合，每行之间用换行符分隔
    cleaned_text = '\n'.join(cleaned_lines)

    # 5. 去除连续的多个空行（保留一个空行作为段落分隔）
    import re
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

    return cleaned_text

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
            model_name=DEEPSEEK_MODEL,
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_BASE = DEEPSEEK_API_BASE,
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
        traceback.print_exc()
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
        traceback.print_exc()
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
                model_name=DEEPSEEK_MODEL,
                openai_api_key=DEEPSEEK_API_KEY,
                openai_api_base=DEEPSEEK_API_BASE,
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
            traceback.print_exc()
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

def extract_text_from_pdf(pdf_path):
    """
    使用 pdfplumber 从 PDF 文件中提取文本内容
    :param pdf_path: PDF 文件的完整路径
    :return: 提取到的文本内容字符串（已清理优化）
    """
    # 初始化空字符串用于存储提取的文本
    text = ""

    # 使用 with 语句打开 PDF 文件，确保文件正确关闭
    with pdfplumber.open(pdf_path) as pdf:
        # 获取 PDF 总页数
        total_pages = len(pdf.pages)
        print(f"【PDF 解析】PDF 文件共 {total_pages} 页")

        # 遍历 PDF 中的每一页
        for i, page in enumerate(pdf.pages):
            # 提取当前页面的文本
            page_text = page.extract_text()

            if page_text:  # 检查页面是否有文本内容
                print(f"【PDF 解析】第 {i+1} 页提取到 {len(page_text)} 字符")
                # 清理页面文本后添加到总文本中
                cleaned_page_text = clean_text(page_text)
                text += cleaned_page_text + "\n\n"  # 每页之间添加两个空行分隔
            else:
                print(f"【PDF 解析】第 {i+1} 页无文本内容")

    # 对整体文本进行最终清理
    final_text = clean_text(text)
    print(f"【PDF 解析】最终文本长度: {len(final_text)} 字符")

    return final_text

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
            model_name=DEEPSEEK_MODEL,      # 使用 DeepSeek 模型
            openai_api_key=DEEPSEEK_API_KEY, # 设置 API Key
            openai_api_base=DEEPSEEK_API_BASE, # 设置 API 地址
            temperature=0.0,                # 温度设置为 0，确保输出稳定
            max_tokens=500                  # 限制输出长度
        )
        print("✅ LangChain 模型初始化成功")
        print(f"   模型名称: {DEEPSEEK_MODEL}")
        print(f"   API 地址: {DEEPSEEK_API_BASE}")
    except Exception as e:
        print("❌ LangChain 模型初始化失败")
        print(f"   错误信息: {str(e)}")
        traceback.print_exc()  # 打印完整的错误堆栈
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
        traceback.print_exc()
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
        traceback.print_exc()
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
        print(f"   API Key 前 10 位: {DEEPSEEK_API_KEY[:10]}...")

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
        traceback.print_exc()
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
        traceback.print_exc()
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

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Flask 路由：首页，处理文件上传请求
    支持 GET 和 POST 方法：
    - GET: 显示上传表单（无文本）
    - POST: 处理文件上传、OCR 识别、AI 分析并显示结果
    """
    # 初始化提取的文本、文件名和提取的字段
    extracted_text = ""
    filename = ""
    contract_fields = None
    ocr_method = ""  # 记录使用的识别方式

    if request.method == 'POST':
        # 检查请求中是否包含文件部分
        if 'file' not in request.files:
            flash('未选择文件！', 'danger')
            return render_template('index.html', text="", filename="", fields=None, ocr_method="")

        # 获取上传的文件对象
        file = request.files['file']

        # 检查文件名是否为空
        if file.filename == '':
            flash('请选择一个文件！', 'danger')
            return render_template('index.html', text="", filename="", fields=None, ocr_method="")

        # 检查文件类型是否允许
        if file and allowed_file(file.filename):
            # 保存原始文件名（用于显示）
            original_filename = file.filename
            # 使用安全文件名保存文件（用于存储，防止路径遍历攻击）
            safe_filename = secure_filename(file.filename)
            # 如果安全文件名被处理为空（如中文文件名），生成一个唯一文件名
            if not safe_filename:
                ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'pdf'
                safe_filename = f"upload_{os.urandom(8).hex()}.{ext}"
            # 构建文件保存路径
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
            # 将原始文件名赋值给 filename 用于页面显示
            filename = original_filename
            # 获取文件类型
            file_type = get_file_type(original_filename)

            try:
                # 保存上传的文件到指定目录
                file.save(file_path)
                flash('文件上传成功！', 'success')

                # ==========================================================
                # 根据文件类型选择处理方式
                # ==========================================================
                if file_type == 'pdf':
                    # ==========================================================
                    # PDF 文件：仅使用 pdfplumber 提取文本，不使用 OCR
                    # ==========================================================
                    print("\n" + "=" * 60)
                    print("📄 【PDF 文件】使用 pdfplumber 提取文本")
                    print("=" * 60)
                    extracted_text = extract_text_from_pdf(file_path)

                    # 检查 pdfplumber 是否成功提取到文本
                    if extracted_text.strip():
                        print("✅ pdfplumber 文本提取成功！")
                        print("📄 当前识别模式：pdfplumber（PDF文本提取）")
                        ocr_method = "pdfplumber"
                        flash('PDF文本提取成功（pdfplumber）！', 'success')
                    else:
                        # pdfplumber 提取失败，说明是扫描件
                        print("⚠️ pdfplumber 未能提取到文本，这可能是扫描件")
                        print("📄 当前识别模式：pdfplumber（无文本内容）")
                        ocr_method = "pdfplumber"
                        flash('当前 PDF 为扫描件，请上传图片版本或安装 Poppler 启用 PDF OCR', 'warning')
                        extracted_text = ""
                else:
                    # ==========================================================
                    # 图片文件（PNG/JPG/JPEG）：使用 DeepSeek OCR
                    # ==========================================================
                    print("\n" + "=" * 60)
                    print(f"🖼️ 【图片文件】使用 DeepSeek OCR 识别")
                    print("=" * 60)
                    print("⏳ OCR识别中...")
                    flash('OCR识别中...', 'info')

                    # 调用 DeepSeek OCR（只处理图片，不会处理 PDF）
                    ocr_result = extract_text_using_deepseek_ocr(file_path, file_type)

                    # 检查 OCR 是否成功
                    if ocr_result and ocr_result.get('error') is None:
                        extracted_text = ocr_result.get('text', '')
                        pages = ocr_result.get('pages', 0)
                        ocr_method = "DeepSeek OCR"
                        print(f"✅ OCR识别完成！共识别 {pages} 张图片")
                        print(f"🔍 当前识别模式：DeepSeek OCR")
                        flash(f'OCR识别完成！共识别 {pages} 张图片', 'success')
                    else:
                        error_msg = ocr_result.get('error', '未知错误') if ocr_result else 'OCR 返回为空'
                        print(f"❌ DeepSeek OCR 失败: {error_msg}")
                        flash(f'OCR 识别失败：{error_msg}', 'danger')
                        extracted_text = ""

                # ==========================================================
                # AI 分析：检查是否成功获取文本，然后进行字段提取
                # ==========================================================
                if extracted_text.strip():
                    print("\n" + "=" * 60)
                    print("🤖 【第三步】开始 AI 合同字段分析")
                    print("=" * 60)

                    # 使用 LangChain + DeepSeek API 提取合同字段
                    flash('正在使用 AI 分析合同...', 'info')
                    contract_fields = extract_contract_fields(extracted_text)

                    # 检查是否成功提取字段
                    if contract_fields and not contract_fields.get('error'):
                        flash('AI 字段提取完成！', 'success')
                    else:
                        # 显示详细的错误信息
                        error_msg = contract_fields.get('error', '未知错误') if contract_fields else '返回结果为空'
                        flash(f'AI 分析失败：{error_msg}', 'danger')
                else:
                    flash('无法提取合同文本，请确认文件是有效的 PDF 或图片', 'warning')

            except Exception as e:
                # 捕获处理过程中的异常
                flash(f'处理文件时出错：{str(e)}', 'danger')
                traceback.print_exc()
                # 如果文件已保存，删除它
                if os.path.exists(file_path):
                    os.remove(file_path)
                # 清空提取的文本
                extracted_text = ""
                ocr_method = ""

    # GET 请求或处理完成后，渲染首页并传递提取的文本和字段
    return render_template('index.html',
                           text=extracted_text,
                           filename=filename,
                           fields=contract_fields,
                           ocr_method=ocr_method)

if __name__ == '__main__':
    """
    应用入口点：启动 Flask 开发服务器
    - debug=True: 启用调试模式，代码修改后自动重启
    """
    # 确保必要的目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    print("\n" + "=" * 60)
    print("🚀 智能合同字段提取系统启动中...")
    print("=" * 60)
    print(f"   Flask 版本: 已加载")
    print(f"   支持文件: PDF, PNG, JPG, JPEG")
    print(f"   PDF 解析: pdfplumber")
    print(f"   图片 OCR: DeepSeek Vision API")
    print(f"   AI 模型: {DEEPSEEK_MODEL}")
    print(f"   访问地址: http://127.0.0.1:5001/")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5001)
