"""
TXT Loader(Sprint 4 - v0.6.0)

职责:
- 加载纯文本文件(.txt),按 UTF-8 读取
- txt 无页码,视为单页(page_number=1)

容错:
- UTF-8 解码失败时回退 GBK(兼容中文 Windows 文本)
"""
from app.utils.text_utils import clean_text
from app.extensions.logger import logger
from .base import BaseLoader, Page


class TxtLoader(BaseLoader):
    """纯文本加载器(UTF-8 / GBK 兼容)"""

    @property
    def supported_extensions(self) -> tuple:
        return ('txt',)

    def load(self, file_path: str) -> list:
        text = None
        # 优先 UTF-8,失败回退 GBK(兼容 Windows 中文 txt)
        for encoding in ('utf-8', 'gbk'):
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read()
                logger.info('[Knowledge:txt_loader] TXT 读取成功(encoding=%s): %s',
                            encoding, file_path)
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.exception('[Knowledge:txt_loader] TXT 读取失败: %s', file_path)
                raise

        if text is None:
            raise ValueError('TXT 文件解码失败(不支持 UTF-8 / GBK)')

        text = clean_text(text)
        return [Page(page_number=1, text=text)]
