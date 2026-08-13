"""
文件工具函数
从 legacy/app.py 原样迁移;唯一变更:配置来源由模块级 app 全局改为 current_app.config。

Sprint 6.2 Transaction Hotfix 新增:
- cleanup_generated_file():安全删除生成的 Word 文件(事务回滚时调用)
- cleanup_temp_file():安全删除临时文件
- cleanup_temp_files():批量清理临时文件
"""
import os

from flask import current_app


def allowed_file(filename):
    """
    检查文件名是否符合允许的扩展名要求
    :param filename: 上传的文件名
    :return: 如果扩展名在允许列表中返回 True,否则 False
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def get_file_type(filename):
    """
    获取文件类型(PDF 或图片)
    :param filename: 上传的文件名
    :return: 'pdf' 或 'image'
    """
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext == 'pdf':
        return 'pdf'
    else:
        return 'image'


# ============================================================
# Sprint 6.2 Transaction Hotfix:资源清理工具
# ============================================================
def cleanup_generated_file(file_path):
    """
    安全删除生成的 Word 文件(事务回滚时调用)

    使用场景:
    - Generation Pipeline 事务失败后,清理已渲染的 Word 文件
    - 保证数据库与文件系统一致性(DB rollback → 文件也删除)

    :param file_path: 生成的文件绝对路径
    :return: bool 是否成功删除(True=已删除/不存在,False=删除失败)
    """
    if not file_path:
        return True

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except OSError:
        # 不抛异常,仅记录(清理失败不应影响主流程)
        try:
            from app.extensions.logger import logger
            logger.warning('[FileUtils] 清理生成文件失败: %s', file_path)
        except Exception:
            pass
        return False


def cleanup_temp_file(file_path):
    """
    安全删除临时文件

    使用场景:
    - Word 渲染过程中的临时文件清理
    - 事务失败后的临时文件兜底清理

    :param file_path: 临时文件绝对路径
    :return: bool 是否成功删除(True=已删除/不存在,False=删除失败)
    """
    return cleanup_generated_file(file_path)


def cleanup_temp_files(file_paths):
    """
    批量清理临时文件

    :param file_paths: 文件路径列表
    :return: int 成功清理的文件数量
    """
    cleaned = 0
    for fp in file_paths or []:
        if cleanup_temp_file(fp):
            cleaned += 1
    return cleaned
