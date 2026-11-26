"""把归档清单中的文件转换为浏览器可安全展示的内容。"""
import csv
import io
import zipfile
from html import escape
from pathlib import Path
from xml.etree import ElementTree

from openpyxl import load_workbook
import xlrd

_ROW_LIMIT = 150
_COL_LIMIT = 30
_TEXT_LIMIT = 300_000


def _zip_within_limit(data: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        return len(entries) <= 2000 and sum(entry.file_size for entry in entries) <= 50 * 1024 * 1024


def _page(title: str, content: str) -> bytes:
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<style>body{font:14px/1.6 system-ui,sans-serif;color:#253044;margin:20px}"
            "h1{font-size:18px}h2{font-size:15px;margin-top:22px}table{border-collapse:collapse;width:100%;margin:10px 0}"
            "td,th{border:1px solid #d9e0e8;padding:5px 8px;text-align:left;white-space:pre-wrap}"
            "pre{white-space:pre-wrap;word-break:break-word;background:#f5f7fa;padding:14px}"
            ".hint{color:#637184}</style><h1>" + escape(title) + "</h1>" + content + "</html>").encode("utf-8")


def _table(rows):
    html_rows = []
    for index, row in enumerate(rows):
        if index >= _ROW_LIMIT:
            break
        cells = [f"<td>{escape(str(value if value is not None else ''))}</td>"
                 for value in list(row)[:_COL_LIMIT]]
        html_rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(html_rows) + "</table>"


def _spreadsheet(data: bytes, suffix: str):
    if len(data) > 20 * 1024 * 1024:
        return "<p class='hint'>文件超过在线表格预览上限，请在归档包中查看完整文件。</p>"
    if suffix == ".xlsx" and not _zip_within_limit(data):
        return "<p class='hint'>工作簿展开内容过大，请在归档包中查看完整文件。</p>"
    sections = []
    if suffix == ".xlsx":
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            for sheet in workbook.worksheets:
                sections.append(f"<h2>{escape(sheet.title)}</h2>" + _table(sheet.iter_rows(values_only=True)))
        finally:
            workbook.close()
    else:
        workbook = xlrd.open_workbook(file_contents=data)
        for sheet in workbook.sheets():
            sections.append(f"<h2>{escape(sheet.name)}</h2>" +
                            _table(sheet.row_values(index) for index in range(sheet.nrows)))
    return "<p class='hint'>每张工作表显示前 150 行、前 30 列；完整内容请查看归档包。</p>" + "".join(sections)


def _office_text(data: bytes, suffix: str):
    if not _zip_within_limit(data):
        return "文档展开内容过大，请在归档包中查看完整文件。"
    output = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = (["word/document.xml"] if suffix == ".docx" else
                 sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")))
        for name in names[:100]:
            info = archive.getinfo(name)
            if info.file_size > 4 * 1024 * 1024:
                output.append("文档内容超过在线预览上限")
                continue
            root = ElementTree.fromstring(archive.read(info))
            paragraphs = []
            for node in root.iter():
                if node.tag.endswith("}p"):
                    text = "".join(part.text or "" for part in node.iter() if part.tag.endswith("}t"))
                    if text.strip():
                        paragraphs.append(text)
            output.append("\n".join(paragraphs[:500]))
    return "\n\n".join(output)


def render_file(name: str, data: bytes) -> tuple[bytes, str]:
    """PDF/图片返回原件;其他格式返回转义后的只读 HTML 内容预览。"""
    suffix = Path(name).suffix.lower()
    if data.startswith(b"%PDF-"):
        return data, "application/pdf"
    signatures = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
                  (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"))
    for signature, media_type in signatures:
        if data.startswith(signature):
            return data, media_type
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return data, "image/webp"

    try:
        if suffix in (".xlsx", ".xls"):
            content = _spreadsheet(data, suffix)
        elif suffix in (".docx", ".pptx"):
            content = "<pre>" + escape(_office_text(data, suffix)[:_TEXT_LIMIT]) + "</pre>"
        elif suffix == ".csv":
            text = data.decode("utf-8-sig")
            content = _table(csv.reader(io.StringIO(text)))
        elif suffix in (".txt", ".json", ".xml", ".html", ".md", ".log"):
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = data.decode("gb18030", errors="replace")
            content = "<pre>" + escape(text[:_TEXT_LIMIT]) + "</pre>"
        elif suffix == ".zip":
            if not _zip_within_limit(data):
                raise ValueError("压缩包内容过大")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                content = "<p class='hint'>压缩包内部文件列表：</p><pre>" + escape(
                    "\n".join(archive.namelist()[:500])) + "</pre>"
        else:
            content = ("<p class='hint'>此格式暂不支持可视化，显示文件开头的十六进制内容；完整文件在归档包中。</p>"
                       "<pre>" + escape(data[:512].hex(" ")) + "</pre>")
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError, xlrd.XLRDError):
        content = "<p class='hint'>文件格式无法解析；完整文件仍可从归档包下载。</p>"
    return _page(name, content), "text/html; charset=utf-8"
