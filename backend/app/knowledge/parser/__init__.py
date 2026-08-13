"""
文档解析编排(Sprint 4 - v0.6.0)

职责:
- 按文件扩展名选择对应 Loader
- 调用 loader.load() 得到 Page 列表
- 合并全文,并构建 page_map(每页在全文中的 [start_offset, end_offset])
  供 chunker 计算 chunk 的 page_number

输出 ParsedDocument:
- text: 全文(各页用双换行拼接,清洗后)
- page_count: 页数
- page_map: [{page_number, start_offset, end_offset}]

设计说明:
- 不直接 import 具体 loader(通过 LOADER_REGISTRY 字典映射,便于扩展)
- 解析层不依赖 chunker / embedding / vectorstore
"""
import os
from dataclasses import dataclass
from typing import List

from app.extensions.logger import logger
from app.knowledge.loader import (
    BaseLoader, PdfLoader, DocxLoader, TxtLoader,
)


@dataclass
class PageRange:
    """页在全文中的字符区间"""
    page_number: int
    start_offset: int
    end_offset: int


@dataclass
class ParsedDocument:
    """解析产物:全文 + 页区间映射"""
    text: str
    page_count: int
    page_map: List[PageRange]


# ---------- Loader 注册表(扩展名 → Loader 类)----------
_LOADER_REGISTRY = {
    'pdf': PdfLoader,
    'docx': DocxLoader,
    'txt': TxtLoader,
}


def get_supported_extensions() -> tuple:
    """知识库支持的文件扩展名"""
    return tuple(_LOADER_REGISTRY.keys())


def _get_loader(file_path: str) -> BaseLoader:
    """按扩展名选择 Loader"""
    ext = file_path.rsplit('.', 1)[1].lower() if '.' in file_path else ''
    LoaderCls = _LOADER_REGISTRY.get(ext)
    if LoaderCls is None:
        raise ValueError(f'不支持的知识文档类型: .{ext}(允许: {", ".join(_LOADER_REGISTRY)})')
    return LoaderCls()


def parse_document(file_path: str) -> ParsedDocument:
    """
    解析文档:文件 → 全文 + 页区间映射

    :param file_path: 文件绝对路径
    :return: ParsedDocument
    :raises: ValueError(不支持的类型)/ 解析异常
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f'文件不存在: {file_path}')

    loader = _get_loader(file_path)
    pages = loader.load(file_path)

    if not pages:
        return ParsedDocument(text='', page_count=0, page_map=[])

    # 合并各页为全文(页间双换行),并记录每页 offset 区间
    parts = []
    page_map = []
    cursor = 0
    for page in pages:
        page_text = page.text
        if not page_text:
            # 空页仍记录区间(长度 0),保留页码连续性
            page_map.append(PageRange(
                page_number=page.page_number,
                start_offset=cursor,
                end_offset=cursor,
            ))
            continue
        # 页间分隔:双换行(与 chunker 段落切分一致)
        segment = page_text
        parts.append(segment)
        start = cursor
        end = cursor + len(segment)
        page_map.append(PageRange(
            page_number=page.page_number,
            start_offset=start,
            end_offset=end,
        ))
        cursor = end
        # 加双换行分隔(计入下一页起始 cursor)
        sep = '\n\n'
        parts.append(sep)
        cursor += len(sep)

    raw_text = ''.join(parts)
    # 注:不在此处对全文再做 clean_text —— 各 loader 已对每页文本清洗,
    # 页间用 \n\n 分隔(已是合法段落分隔)。若再清洗会改变文本长度,
    # 导致 page_map 的 offset 与 text 失配,chunk 的 page_number 定位错误。
    text = raw_text

    logger.info('[Knowledge:parser] 解析完成: pages=%s text_length=%s',
                len(page_map), len(text))
    return ParsedDocument(text=text, page_count=len(page_map), page_map=page_map)


def locate_page(page_map: List[PageRange], offset: int) -> int:
    """
    根据字符偏移定位页码(供 chunker 使用)

    :param page_map: 页区间列表
    :param offset: 字符偏移
    :return: 页码(1-based);无法定位返回 0
    """
    for pr in page_map:
        if pr.start_offset <= offset < pr.end_offset:
            return pr.page_number
        # 空页(start==end)且 offset 恰好等于其 start,也归属该页
        if pr.start_offset == pr.end_offset and offset == pr.start_offset:
            return pr.page_number
    # 落在页间分隔符:取前一个非空页
    last_page = 0
    for pr in page_map:
        if pr.start_offset <= offset:
            if pr.end_offset > pr.start_offset:
                last_page = pr.page_number
        else:
            break
    return last_page
