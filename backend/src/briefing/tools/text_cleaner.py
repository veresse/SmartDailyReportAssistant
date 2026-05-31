"""文本清洗工具：将 RSS 原始内容转换为纯净的 Markdown 文本。"""

import re

_HTML_TAG_RE = re.compile(r'<[^>]+>')
_BASE64_RE = re.compile(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+')
_UNICODE_GARBAGE_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
_MULTI_NEWLINE_RE = re.compile(r'\n{3,}')
_MULTI_SPACE_RE = re.compile(r' {2,}')


def clean_raw_content(raw_html: str, max_chars: int = 5000) -> str:
    """剔除 HTML 残留、Base64 图片、乱码，返回纯净文本。"""
    if not raw_html:
        return ""
    text = _BASE64_RE.sub('', raw_html)
    text = _HTML_TAG_RE.sub('', text)
    text = _UNICODE_GARBAGE_RE.sub('', text)
    text = _MULTI_NEWLINE_RE.sub('\n\n', text)
    text = _MULTI_SPACE_RE.sub(' ', text)
    return text.strip()[:max_chars]


def extract_feature_text(cleaned_text: str, length: int = 500) -> str:
    """提取前 N 字作为向量化特征文本。"""
    if not cleaned_text:
        return ""
    return cleaned_text[:length]
