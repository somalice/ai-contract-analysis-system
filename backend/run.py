"""
后端入口脚本
启动方式:python run.py
访问地址:http://127.0.0.1:5001/
"""
import os
from dotenv import load_dotenv
from app import create_app

# 加载 backend/.env
load_dotenv()

app = create_app()


if __name__ == '__main__':
    # 确保上传目录存在(create_app 已保证,此处保留与 legacy 一致的语义)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    print("\n" + "=" * 60)
    print("🚀 智能合同与投标管理平台启动中...(v1.0.0)")
    print("=" * 60)
    print(f"   Flask 版本: 已加载")
    print(f"   支持文件: PDF, PNG, JPG, JPEG, DOCX, TXT")
    print(f"   PDF 解析: pdfplumber")
    print(f"   图片 OCR: DeepSeek Vision API")
    print(f"   AI 模型: {app.config['DEEPSEEK_MODEL']}")
    print(f"   访问地址: http://127.0.0.1:5001/")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5001)
