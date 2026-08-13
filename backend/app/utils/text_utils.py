"""
文本清理工具函数
从 legacy/app.py 原样迁移。
"""
import re


def clean_text(text):
    """
    清理提取的文本,提高可读性
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

        # 2. 去除行内多余的连续空格(多个空格变成一个空格)
        line = ' '.join(line.split())

        # 3. 只保留非空行(但保留段落分隔的空行)
        if line:
            cleaned_lines.append(line)

    # 4. 将处理后的行重新组合,每行之间用换行符分隔
    cleaned_text = '\n'.join(cleaned_lines)

    # 5. 去除连续的多个空行(保留一个空行作为段落分隔)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

    return cleaned_text
