#!/usr/bin/env python3
"""
階層型Markdown → Excel USDM 逆変換スクリプト

Markdownファイル群を解析し、新規Excelファイルとして保存する。
テンプレートExcel不要。

Usage:
    python3 md2usdm.py <md_dir> [output.xlsx]
"""

import os
import re
import sys
from dataclasses import dataclass, field

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock, InlineFont
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.worksheet.properties import Outline


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Specification:
    ss_type: str
    number: str
    content: str
    spec_id: str
    usdm_ref: str
    extras: dict = field(default_factory=dict)


@dataclass
class TtSubsection:
    name: str
    specs: list = field(default_factory=list)


@dataclass
class LowerReq:
    req_id: str
    text: str
    spec_id: str
    reason: str
    explanation: str
    subsections: list = field(default_factory=list)
    specs: list = field(default_factory=list)


@dataclass
class UpperReq:
    req_id: str
    text: str
    spec_id: str
    reason: str
    explanation: str
    lower_reqs: list = field(default_factory=list)


@dataclass
class Section:
    number: str
    name: str
    upper_reqs: list = field(default_factory=list)


@dataclass
class SheetData:
    sheet_name: str
    config: dict
    component_info: str
    component_reason: str
    component_explanation: str
    separator_label: str
    sections: list = field(default_factory=list)
    upper_reqs: list = field(default_factory=list)


@dataclass
class HeaderEntry:
    col_str: str
    text: str
    merge_str: str


@dataclass
class ComponentInfo:
    doc_id: str
    spec_id: str
    info: str
    reason: str
    explanation: str


# ---------------------------------------------------------------------------
# Rich Text Reverse Conversion (Markdown → openpyxl cell values)
# ---------------------------------------------------------------------------

DEFAULT_FONT = Font(name='ＭＳ ゴシック', size=9)
RED_FONT = Font(name='ＭＳ ゴシック', size=9, color='FFFF0000')
STRIKE_FONT = Font(name='ＭＳ ゴシック', size=9, strikethrough=True)
RED_STRIKE_FONT = Font(name='ＭＳ ゴシック', size=9, color='FFFF0000', strikethrough=True)

RED_INLINE = InlineFont(rFont='ＭＳ ゴシック', sz=9, color='FFFF0000')
STRIKE_INLINE = InlineFont(rFont='ＭＳ ゴシック', sz=9, strike=True)
RED_STRIKE_INLINE = InlineFont(rFont='ＭＳ ゴシック', sz=9, color='FFFF0000', strike=True)
DEFAULT_INLINE = InlineFont(rFont='ＭＳ ゴシック', sz=9)

_FORMAT_PATTERN = re.compile(
    r'(\*\*~~(.*?)~~\*\*)'
    r'|(\*\*(.*?)\*\*)'
    r'|(~~(.*?)~~)',
    re.DOTALL
)


def parse_md_formatting(text):
    if not text:
        return [("", False, False)]
    segments = []
    last_end = 0
    for m in _FORMAT_PATTERN.finditer(text):
        if m.start() > last_end:
            segments.append((text[last_end:m.start()], False, False))
        if m.group(1):
            segments.append((m.group(2), True, True))
        elif m.group(3):
            segments.append((m.group(4), True, False))
        elif m.group(5):
            segments.append((m.group(6), False, True))
        last_end = m.end()
    if last_end < len(text):
        segments.append((text[last_end:], False, False))
    if len(segments) > 1:
        segments = [(t, r, s) for t, r, s in segments if t]
    return segments if segments else [("", False, False)]


def _get_inline_font(is_red, is_strike):
    if is_red and is_strike:
        return RED_STRIKE_INLINE
    if is_red:
        return RED_INLINE
    if is_strike:
        return STRIKE_INLINE
    return DEFAULT_INLINE


def _get_cell_font(is_red, is_strike):
    if is_red and is_strike:
        return RED_STRIKE_FONT
    if is_red:
        return RED_FONT
    if is_strike:
        return STRIKE_FONT
    return DEFAULT_FONT


def md_to_cell(text):
    if not text:
        return ("", DEFAULT_FONT)
    segments = parse_md_formatting(text)
    formats = set((r, s) for _, r, s in segments if _)
    if not formats:
        return ("", DEFAULT_FONT)
    if len(formats) == 1:
        is_red, is_strike = formats.pop()
        plain = "".join(t for t, _, _ in segments)
        return (plain, _get_cell_font(is_red, is_strike))
    blocks = []
    for seg_text, is_red, is_strike in segments:
        if not seg_text:
            continue
        inline_font = _get_inline_font(is_red, is_strike)
        blocks.append(TextBlock(inline_font, seg_text))
    if not blocks:
        return ("", DEFAULT_FONT)
    return (CellRichText(blocks), None)


# ---------------------------------------------------------------------------
# Cell Style Constants
# ---------------------------------------------------------------------------

GRAY_FILL = PatternFill(start_color='FFD8D8D8', end_color='FFD8D8D8', fill_type='solid')
BLUE_FILL = PatternFill(start_color='FFCCFFFF', end_color='FFCCFFFF', fill_type='solid')
YELLOW_FILL = PatternFill(start_color='FFFFFF99', end_color='FFFFFF99', fill_type='solid')
ORANGE_FILL = PatternFill(start_color='FFFFCC99', end_color='FFFFCC99', fill_type='solid')

# Template format fills (USDMテンプレート互換)
TMPL_U_FILL = PatternFill(start_color='FFE2EFDA', end_color='FFE2EFDA', fill_type='solid')
TMPL_UU_FILL = PatternFill(start_color='FFFFF2CC', end_color='FFFFF2CC', fill_type='solid')
DARK_GRAY_FILL = PatternFill(start_color='FF595959', end_color='FF595959', fill_type='solid')
WHITE_FONT = Font(name='ＭＳ ゴシック', size=9, color='FFFFFFFF')
HEADER_FONT = Font(name='ＭＳ ゴシック', size=9)

THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin'),
)
BORDER_SPAN_LEFT = Border(
    left=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'),
)
BORDER_SPAN_MID = Border(
    top=Side(style='thin'), bottom=Side(style='thin'),
)
BORDER_SPAN_RIGHT = Border(
    right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'),
)
BORDER_VERT_ONLY = Border(
    left=Side(style='thin'), right=Side(style='thin'),
)
BORDER_VERT_TOP = Border(
    left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'),
)
BORDER_AUTO_COL = Border(
    right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'),
)
NO_BORDER = Border()

BORDER_VERT_BOTTOM = Border(
    left=Side(style='thin'), right=Side(style='thin'), bottom=Side(style='thin'),
)

WRAP_ALIGNMENT = Alignment(wrap_text=True, vertical='top')
NOWRAP_ALIGNMENT = Alignment(wrap_text=False, vertical='top')
CENTER_TOP = Alignment(horizontal='center', vertical='top', wrap_text=True)
CENTER_CENTER = Alignment(horizontal='center', vertical='center', wrap_text=False)
CENTER_WRAP = Alignment(horizontal='center', vertical='center', wrap_text=True)


# ---------------------------------------------------------------------------
# Markdown Table Cell Unescape
# ---------------------------------------------------------------------------

def unescape_table_cell(text):
    if not text:
        return ""
    text = text.replace("<br>", "\n")
    text = text.replace("\\|", "|")
    return text


# ---------------------------------------------------------------------------
# Markdown Parsers
# ---------------------------------------------------------------------------

def read_md(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _detect_header_merges(col_strs, r2_vals, r3_vals, r4_vals=None):
    """Detect merge ranges from transposed header table.

    Markers: ← = horizontal merge end, ↑ = vertical merge, ↖ = both.
    Vertical extent determined from row 4 markers.
    """
    entries = []
    n = len(col_strs)
    r2 = list(r2_vals) + [""] * max(0, n - len(r2_vals))
    r3 = list(r3_vals) + [""] * max(0, n - len(r3_vals))
    r4 = list(r4_vals or []) + [""] * max(0, n - len(r4_vals or []))

    def _is_marker(val):
        return val in ("←", "↑", "↖")

    def _is_h_end(val):
        return val in ("←", "↖")

    def _is_vert(val):
        return val in ("↑", "↖")

    # Process row 2: detect horizontal merges
    i = 0
    while i < n:
        if r2[i] and not _is_marker(r2[i]):
            # Find merge end: look for ← marker
            j = i + 1
            while j < n and not r2[j]:
                j += 1
            if j < n and _is_h_end(r2[j]):
                j += 1
            else:
                j = i + 1

            # Vertical extent: sub-headers in row 3 → row 2 only; else check row 4
            has_sub_text = any(r3[k] and not _is_marker(r3[k]) for k in range(i, min(j, n)))
            has_vert_r4 = any(_is_vert(r4[k]) for k in range(i, min(j, n)))
            if has_sub_text:
                max_row = 2  # Sub-headers below → horizontal only
            elif has_vert_r4:
                max_row = 4
            else:
                max_row = 4  # Default

            start_letter = col_strs[i]
            end_letter = col_strs[j - 1]
            col_str = start_letter if j - i == 1 else f"{start_letter}-{end_letter}"
            merge_str = f"{start_letter}2:{end_letter}{max_row}"
            entries.append(HeaderEntry(col_str=col_str, text=r2[i], merge_str=merge_str))
            i = j
        else:
            i += 1

    # Process row 3: detect entries (non-marker text)
    i = 0
    while i < n:
        if r3[i] and not _is_marker(r3[i]):
            j = i + 1
            while j < n and not r3[j]:
                j += 1
            if j < n and _is_h_end(r3[j]):
                j += 1
            else:
                j = i + 1

            start_letter = col_strs[i]
            end_letter = col_strs[j - 1]
            col_str = start_letter if j - i == 1 else f"{start_letter}-{end_letter}"
            merge_str = f"{start_letter}3:{end_letter}4"
            entries.append(HeaderEntry(col_str=col_str, text=r3[i], merge_str=merge_str))
            i = j
        else:
            i += 1

    return entries


def _parse_col_marker(col_str):
    """Parse column marker formatting from header row.

    Returns (clean_col, marker_type):
      **col** → ('col', 'bold')   = u-row start column
      ~~col~~ → ('col', 'strike') = uu-row start column
      `col`   → ('col', 'code')   = marker column
      col     → ('col', None)     = normal column
    """
    if col_str.startswith("**") and col_str.endswith("**"):
        return col_str[2:-2], 'bold'
    if col_str.startswith("~~") and col_str.endswith("~~"):
        return col_str[2:-2], 'strike'
    if col_str.startswith("`") and col_str.endswith("`"):
        return col_str[1:-1], 'code'
    return col_str, None


def _detect_row1_merges(col_strs, r1_vals):
    """Detect merge ranges from single-row header (row 1).

    Used for template format where header is only row 1.
    """
    entries = []
    n = len(col_strs)
    r1 = list(r1_vals) + [""] * max(0, n - len(r1_vals))
    i = 0
    while i < n:
        if r1[i] and r1[i] not in ("←", "↑", "↖"):
            j = i + 1
            while j < n and r1[j] == "←":
                j += 1
            start = col_strs[i]
            end = col_strs[j - 1]
            col_str = start if j - i == 1 else f"{start}-{end}"
            merge_str = f"{start}1:{end}1"
            entries.append(HeaderEntry(col_str=col_str, text=r1[i], merge_str=merge_str))
            i = j
        else:
            i += 1
    return entries


def parse_top_index(path):
    """Parse top-level index.md.

    Returns: (header_entries, sheet_list, excel_basename, base_col_widths, base_colors, col_markers)
      header_entries: list of HeaderEntry (only rows with header text + merge)
      sheet_list: [(sheet_name, dir_name)]
      excel_basename: str
      base_col_widths: dict {col_letter: width}
      base_colors: (bg_dict, fg_dict) where each is {col_index: '6-digit hex'}
      col_markers: dict {'bold': col_letter, 'strike': col_letter, 'code': col_letter}
    """
    content = read_md(path)

    # Extract title (excel basename)
    m = re.match(r'# (.+)', content)
    excel_basename = m.group(1).strip() if m else ""

    # Parse header table (transposed: columns=Excel cols, rows=properties)
    header_entries = []
    base_col_widths = {}
    bg_colors = {}
    fg_colors = {}
    in_header = False
    header_lines = []
    for line in content.split("\n"):
        if line.strip() == "## ヘッダー":
            in_header = True
            continue
        if in_header and line.startswith("##"):
            in_header = False
            continue
        if in_header and line.startswith("|") and "---" not in line:
            header_lines.append(line)

    if header_lines:
        # Parse transposed table: | 行 | A | B | ... |
        def _parse_row(line):
            cells = [c.strip() for c in line.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            return cells

        rows_by_label = {}
        col_strs = []
        col_markers = {}
        for line in header_lines:
            cells = _parse_row(line)
            if not cells:
                continue
            label = cells[0]
            if label == "行":
                raw_cols = cells[1:]
                col_strs = []
                for raw in raw_cols:
                    clean, marker_type = _parse_col_marker(raw)
                    col_strs.append(clean)
                    if marker_type:
                        col_markers[marker_type] = clean
            else:
                rows_by_label[label] = cells[1:]

        width_row = rows_by_label.get("列", [""] * len(col_strs))

        # Parse widths
        for i, col_str in enumerate(col_strs):
            w = width_row[i] if i < len(width_row) else ""
            if w:
                try:
                    base_col_widths[col_str] = float(w)
                except ValueError:
                    pass

        # Detect header merges: row "1" (template) or rows "2"-"4" (19-column format)
        if "1" in rows_by_label and "2" not in rows_by_label:
            r1_row = rows_by_label["1"]
            header_entries = _detect_row1_merges(col_strs, r1_row)
        else:
            r2_row = rows_by_label.get("2", [""] * len(col_strs))
            r3_row = rows_by_label.get("3", [""] * len(col_strs))
            r4_row = rows_by_label.get("4", [""] * len(col_strs))
            header_entries = _detect_header_merges(col_strs, r2_row, r3_row, r4_row)

        # Parse color rows (expand ← to copy from left)
        def _expand_row(row_vals):
            expanded = list(row_vals)
            for i in range(1, len(expanded)):
                if expanded[i] == "←":
                    expanded[i] = expanded[i - 1]
            return expanded

        bg_row = _expand_row(rows_by_label.get("背景色", [""] * len(col_strs)))
        fg_row = _expand_row(rows_by_label.get("文字色", [""] * len(col_strs)))
        for i, col_str in enumerate(col_strs):
            bg = bg_row[i] if i < len(bg_row) else ""
            fg = fg_row[i] if i < len(fg_row) else ""
            if bg:
                bg_colors[column_index_from_string(col_str)] = bg
            if fg:
                fg_colors[column_index_from_string(col_str)] = fg

    # Parse sheet list
    sheet_list = []
    for m in re.finditer(r'- \[(.+?)\]\(\./(.+?)/index\.md\)', content):
        sheet_list.append((m.group(1), m.group(2)))

    return header_entries, sheet_list, excel_basename, base_col_widths, (bg_colors, fg_colors), col_markers


def parse_component_file(path):
    """Parse component u-file (e.g., PROJECT_ID.md)."""
    content = read_md(path)

    m = re.search(r'^#\s+【(.+?)】', content, re.MULTILINE)
    if m:
        inner = m.group(1)  # e.g., "PROJECT_ID"
        spec_id = f"【{inner}】"
        doc_id = inner
    else:
        # Fallback to old format
        m2 = re.match(r'# 要件 (.+?):', content)
        doc_id = m2.group(1).strip() if m2 else ""
        m3 = re.search(r'\*\*仕様番号\*\*: `(.+?)`', content)
        spec_id = m3.group(1) if m3 else ""

    text, reason, explanation, _ = _parse_req_body(content)

    return ComponentInfo(
        doc_id=doc_id, spec_id=spec_id,
        info=text, reason=reason, explanation=explanation,
    )


def parse_sheet_index(base_dir, sheet_dir, sheet_name, base_comp, base_col_widths=None):
    """Parse sheetNN/index.md → (SheetData, config_info)"""
    dirpath = os.path.join(base_dir, sheet_dir)
    index_path = os.path.join(dirpath, "index.md")
    content = read_md(index_path)

    # Parse header section (extra columns — transposed format)
    header_extra_cols = []
    extra_col_widths = {}
    extra_col_bg = {}
    extra_col_fg = {}
    lines_all = content.split("\n")
    in_header = False
    header_lines = []
    for line in lines_all:
        stripped = line.strip()
        if stripped == "## ヘッダー":
            in_header = True
            continue
        if in_header:
            if stripped.startswith("## ") or (stripped and not stripped.startswith("|") and not stripped.startswith("|-")):
                in_header = False
                continue
            if stripped.startswith("|") and "---" not in stripped:
                header_lines.append(stripped)

    if header_lines:
        def _parse_row_cells(line):
            cells = [c.strip() for c in line.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            return cells

        extra_rows_by_label = {}
        extra_col_strs = []
        for line in header_lines:
            cells = _parse_row_cells(line)
            if not cells:
                continue
            label = cells[0]
            if label == "行":
                extra_col_strs = cells[1:]
            elif label == "列":
                # Old format: | 列 | ヘッダー | 結合 | — detect and fallback
                if len(cells) >= 3 and cells[1] == "ヘッダー":
                    extra_col_strs = []  # Not transposed format
                    break
                extra_rows_by_label[label] = cells[1:]
            else:
                extra_rows_by_label[label] = cells[1:]

        if extra_col_strs:
            # Transposed format
            r2 = extra_rows_by_label.get("2", [""] * len(extra_col_strs))
            r4 = extra_rows_by_label.get("4", [""] * len(extra_col_strs))
            w_row = extra_rows_by_label.get("列", [""] * len(extra_col_strs))

            # Parse extra column colors (expand ←)
            def _expand_row(row_vals):
                expanded = list(row_vals)
                for j in range(1, len(expanded)):
                    if expanded[j] == "←":
                        expanded[j] = expanded[j - 1]
                return expanded

            ebg = _expand_row(extra_rows_by_label.get("背景色", [""] * len(extra_col_strs)))
            efg = _expand_row(extra_rows_by_label.get("文字色", [""] * len(extra_col_strs)))

            for i, col_str in enumerate(extra_col_strs):
                text = r2[i] if i < len(r2) else ""
                has_vert = (r4[i] if i < len(r4) else "") in ("↑", "↖")
                max_row = 4 if has_vert else 2
                merge_str = f"{col_str}2:{col_str}{max_row}"
                if text:
                    header_extra_cols.append((col_str, text, merge_str))
                # Extra column widths
                w = w_row[i] if i < len(w_row) else ""
                if w:
                    try:
                        extra_col_widths[col_str] = float(w)
                    except ValueError:
                        pass
                # Extra column colors
                bg_val = ebg[i] if i < len(ebg) else ""
                fg_val = efg[i] if i < len(efg) else ""
                if bg_val:
                    extra_col_bg[column_index_from_string(col_str)] = bg_val
                if fg_val:
                    extra_col_fg[column_index_from_string(col_str)] = fg_val
        elif not extra_col_strs:
            # Fallback: old format | 列 | ヘッダー | 結合 |
            for line in header_lines:
                cells = _parse_row_cells(line)
                if len(cells) >= 3 and cells[0] not in ("列", "行"):
                    header_extra_cols.append((cells[0], cells[1], cells[2]))

    # Calculate config from header extras
    base_auto = 18  # R column
    num_extras = len(header_extra_cols)
    col_auto = base_auto + num_extras

    # Build column widths: shift base widths for sheets with extra columns
    col_widths = {}
    if base_col_widths:
        for col_key, width in base_col_widths.items():
            if "-" in col_key:
                continue  # Skip multi-column range entries (no individual width)
            col_idx = column_index_from_string(col_key)
            if col_idx > 12 and num_extras > 0:
                new_letter = get_column_letter(col_idx + num_extras)
                col_widths[new_letter] = width
            else:
                col_widths[col_key] = width

    # Merge extra column widths
    col_widths.update(extra_col_widths)

    config = {
        "data_start_row": 9,
        "col_spec_id": 11,
        "col_content": 10,
        "col_usdm_ref": 12,
        "col_auto": col_auto,
        "header_extra_cols": header_extra_cols,
        "col_widths": col_widths,
        "extra_col_colors": (extra_col_bg, extra_col_fg),
        "has_sections": False,
        "section_marker": None,
    }

    # Parse component reason/explanation from ## 要件 / ### 理由 / ### 説明
    req_start = None
    for i, line in enumerate(lines_all):
        if line.strip() in ("## 要件", "## 要求"):
            req_start = i
            break
    if req_start is not None:
        req_content = "\n".join(lines_all[req_start:])
        _, comp_reason, comp_explanation, _ = _parse_req_body(req_content)
    else:
        comp_reason = ""
        comp_explanation = ""
    # Fall back to base component values when not overridden
    if not comp_reason:
        comp_reason = base_comp.reason
    if not comp_explanation:
        comp_explanation = base_comp.explanation

    # Derive separator label from sheet name
    if "." in sheet_name:
        category = sheet_name.split(".", 1)[1]
    else:
        category = sheet_name
    sep_label = f"＜{category}＞"

    sheet = SheetData(
        sheet_name=sheet_name,
        config=config,
        component_info=base_comp.info,
        component_reason=comp_reason,
        component_explanation=comp_explanation,
        separator_label=sep_label,
    )

    # Detect sections vs flat upper reqs
    lines = content.split("\n")
    sections_found = []
    current_section_name = None
    current_links = []

    for line in lines:
        stripped = line.strip()
        # Section heading (## name, but not system headings)
        if stripped.startswith("## ") and stripped not in ("## ヘッダー", "## 上位要件", "## 下位要件", "## 上位要求", "## 下位要求", "## シート一覧", "## 要件", "## 要求"):
            if current_section_name is not None:
                sections_found.append((current_section_name, current_links))
            current_section_name = stripped[3:].strip()
            current_links = []
            continue

        # Flat lower/upper requirement links
        if stripped in ("## 上位要件", "## 下位要件", "## 上位要求", "## 下位要求"):
            current_section_name = None
            current_links = []
            continue

        # Parse links
        link_m = re.match(r'- \[(.+?)\]\((.+?)\.md(?:\s+"(.+?)")?\)', stripped)
        if link_m:
            current_links.append((link_m.group(1), link_m.group(2) + ".md", link_m.group(3) or ""))

    if current_section_name is not None:
        sections_found.append((current_section_name, current_links))

    if sections_found:
        config["has_sections"] = True
        # Detect section_marker: check for explicit metadata, default to "t"
        if re.search(r'セクション区分: `tt`', content):
            config["section_marker"] = "tt"
        else:
            config["section_marker"] = "t"

        for sec_name, links in sections_found:
            num = sec_name.split(".")[0] if "." in sec_name else sec_name
            section = Section(number=num, name=sec_name)
            for link_text, link_path, link_title in links:
                full_path = os.path.join(dirpath, link_path)
                if os.path.exists(full_path):
                    u = parse_u_file(full_path, os.path.dirname(full_path), config)
                    section.upper_reqs.append(u)
            sheet.sections.append(section)
    else:
        # Flat upper requirements
        for line in lines:
            stripped = line.strip()
            link_m = re.match(r'- \[(.+?)\]\((.+?)\.md(?:\s+"(.+?)")?\)', stripped)
            if link_m:
                link_path = link_m.group(2) + ".md"
                full_path = os.path.join(dirpath, link_path)
                if os.path.exists(full_path):
                    u_dir = os.path.dirname(full_path)
                    u = parse_u_file(full_path, u_dir, config)
                    sheet.upper_reqs.append(u)

    return sheet


def _parse_req_body(content):
    lines = content.split("\n")
    section_starts = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ("## 要件", "## 要求"):
            section_starts["要件"] = i
        elif stripped == "### 理由":
            section_starts["理由"] = i
        elif stripped == "### 説明":
            section_starts["説明"] = i
        elif stripped.startswith("## ") and stripped not in ("## 要件", "## 要求"):
            if "_next" not in section_starts:
                section_starts["_next"] = i

    def extract_between(start_key, end_key):
        if start_key not in section_starts:
            return ""
        start = section_starts[start_key] + 1
        end = section_starts.get(end_key, len(lines))
        block = "\n".join(lines[start:end]).strip()
        return block

    text = extract_between("要件", "理由")
    reason_end = "説明" if "説明" in section_starts else "_next"
    reason = extract_between("理由", reason_end)
    explanation = extract_between("説明", "_next")

    if reason == "記載無し":
        reason = ""
    if explanation == "記載無し":
        explanation = ""

    remaining_start = section_starts.get("_next", len(lines))
    remaining = "\n".join(lines[remaining_start:])

    return text, reason, explanation, remaining


def _extract_spec_and_req(content, is_uu=False):
    """Extract spec_id and req_id from '# 【spec】title' format."""
    m = re.search(r'^#\s+【(.+?)】', content, re.MULTILINE)
    if not m:
        # Fallback to old format
        m2 = re.match(r'# 要件 (.+?):', content)
        req_id = m2.group(1).strip() if m2 else ""
        m3 = re.search(r'\*\*仕様番号\*\*: `(.+?)`', content)
        spec_id = m3.group(1) if m3 else ""
        return spec_id, req_id
    inner = m.group(1)  # e.g., "PROJECT_ID_C01" or "PROJECT_ID_C01.DM01"
    spec_id = f"【{inner}】"
    if is_uu and ".DM" in inner:
        req_id = inner.split(".DM", 1)[1]
    elif "_" in inner:
        req_id = inner.split("_", 1)[1]
    else:
        req_id = inner
    return spec_id, req_id


def parse_u_file(path, u_dir, config):
    content = read_md(path)

    spec_id, req_id = _extract_spec_and_req(content)

    text, reason, explanation, remaining = _parse_req_body(content)

    u = UpperReq(
        req_id=req_id, text=text, spec_id=spec_id,
        reason=reason, explanation=explanation,
    )

    # Parse lower requirements from "## 下位要件" links
    seen_uu_files = set()
    for m in re.finditer(r'- \[(.+?)\]\(\./(.+?)\.md(?:\s+"(.+?)")?\)', remaining):
        uu_filename = m.group(2)
        if uu_filename in seen_uu_files:
            continue
        seen_uu_files.add(uu_filename)
        uu_path = os.path.join(u_dir, f"{uu_filename}.md")
        if os.path.exists(uu_path):
            uu = parse_uu_file(uu_path, config)
            u.lower_reqs.append(uu)

    return u


def parse_uu_file(path, config):
    content = read_md(path)

    spec_id, req_id = _extract_spec_and_req(content, is_uu=True)

    text, reason, explanation, remaining = _parse_req_body(content)

    uu = LowerReq(
        req_id=req_id, text=text, spec_id=spec_id,
        reason=reason, explanation=explanation,
    )

    # Parse specifications
    _parse_specs(uu, remaining, config)

    return uu


def _parse_spec_table(table_text, config):
    specs = []
    lines = table_text.strip().split("\n")
    if len(lines) < 3:
        return specs

    header = lines[0]
    headers = [h.strip() for h in header.split("|")]
    headers = [h for h in headers if h]

    col_map = {}
    for i, h in enumerate(headers):
        if h == "種別":
            col_map["ss_type"] = i
        elif h == "#":
            col_map["number"] = i
        elif h == "内容":
            col_map["content"] = i
        elif h == "仕様番号":
            col_map["spec_id"] = i
        elif h == "USDM参照":
            col_map["usdm_ref"] = i
        else:
            # Generic extra column
            col_map[f"extra:{h}"] = i

    for line in lines[2:]:
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c is not None]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))

        def get_col(key):
            idx = col_map.get(key)
            if idx is not None and idx < len(cells):
                return cells[idx]
            return ""

        ss_type = unescape_table_cell(get_col("ss_type")) or "仕様"
        number = unescape_table_cell(get_col("number")).strip()
        content = unescape_table_cell(get_col("content"))
        spec_id = unescape_table_cell(get_col("spec_id"))
        usdm_ref = unescape_table_cell(get_col("usdm_ref"))

        extras = {}
        for key, idx in col_map.items():
            if key.startswith("extra:"):
                col_name = key[6:]
                val = unescape_table_cell(cells[idx] if idx < len(cells) else "")
                if val:
                    extras[col_name] = val

        specs.append(Specification(
            ss_type=ss_type, number=number, content=content,
            spec_id=spec_id, usdm_ref=usdm_ref, extras=extras,
        ))

    return specs


def _parse_specs(uu, content, config):
    spec_section = re.search(r'## 仕様\n\n(.*)', content, re.DOTALL)
    if not spec_section:
        return
    spec_text = spec_section.group(1)
    parts = re.split(r'(### .+)', spec_text)

    current_subsection = None
    i = 0
    while i < len(parts):
        part = parts[i]
        subsec_m = re.match(r'### (.+)', part.strip())
        if subsec_m:
            subsec_name = subsec_m.group(1).strip()
            current_subsection = TtSubsection(name=subsec_name)
            uu.subsections.append(current_subsection)
            i += 1
            continue
        table_match = re.search(r'(\|.+\|(?:\n\|.+\|)*)', part, re.DOTALL)
        if table_match:
            specs = _parse_spec_table(table_match.group(1), config)
            if current_subsection is not None:
                current_subsection.specs.extend(specs)
            else:
                uu.specs.extend(specs)
        i += 1


# ---------------------------------------------------------------------------
# Excel Writer
# ---------------------------------------------------------------------------

def _set_cell(ws, row, col, value, font=None, fill=None, alignment=None, border=None):
    cell = ws.cell(row=row, column=col)
    cell.value = value
    # Prevent openpyxl from treating '=' prefixed strings as formulas
    if isinstance(value, str) and value.startswith('='):
        cell.data_type = 's'
    cell.font = font if font else DEFAULT_FONT
    if fill:
        cell.fill = fill
    if alignment:
        cell.alignment = alignment
    else:
        cell.alignment = WRAP_ALIGNMENT
    cell.border = border if border is not None else THIN_BORDER


def _unescape_spec_newlines(val):
    """Restore actual newlines from literal ``\\n`` in spec_id values.

    usdm2md escapes newlines within spec IDs to the two-character sequence
    ``\\n`` for safe markdown representation.  This reverses the escaping when
    writing values back to Excel.
    """
    if not val or not isinstance(val, str):
        return val
    return val.replace('\\n', '\n')


def _spec_id_auto(spec_id):
    if not spec_id:
        return ""
    m = re.match(r'【(.+)】', spec_id)
    return _unescape_spec_newlines(m.group(1)) if m else ""


def _fill_gap_borders(ws, row, config, border=None):
    if border is None:
        border = THIN_BORDER
    auto_col = config.get("col_auto")
    if not auto_col:
        return
    start = config["col_usdm_ref"] + 1
    for col in range(start, auto_col):
        cell = ws.cell(row=row, column=col)
        if not cell.value:
            _set_cell(ws, row, col, "", border=border)


def _set_outline_level(ws, row, level):
    ws.row_dimensions[row].outline_level = level
    ws.row_dimensions[row].hidden = False


def _count_lines(value):
    if value is None:
        return 1
    if isinstance(value, CellRichText):
        text = "".join(str(block) for block in value)
    else:
        text = str(value)
    if not text:
        return 1
    return max(1, text.count("\n") + 1)


def _adjust_row_height(ws, row, *values):
    max_lines = 1
    for v in values:
        max_lines = max(max_lines, _count_lines(v))
    if max_lines > 1:
        ws.row_dimensions[row].height = 13.5 * max_lines


def _parse_merge_range(merge_str):
    """Parse 'B2:B4' or 'C2:J4' into (min_col, min_row, max_col, max_row)."""
    m = re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', merge_str)
    if not m:
        # Single cell like "B2:B2"
        m2 = re.match(r'([A-Z]+)(\d+)', merge_str)
        if m2:
            c = column_index_from_string(m2.group(1))
            r = int(m2.group(2))
            return c, r, c, r
        return None
    return (
        column_index_from_string(m.group(1)), int(m.group(2)),
        column_index_from_string(m.group(3)), int(m.group(4)),
    )


def _make_header_fill(hex6):
    """Create PatternFill from 6-digit hex color string."""
    return PatternFill(start_color=f'FF{hex6}', end_color=f'FF{hex6}', fill_type='solid')


def _make_header_font(hex6):
    """Create Font from 6-digit hex color string."""
    return Font(name='ＭＳ ゴシック', size=9, color=f'FF{hex6}')


def write_header_rows(ws, header_entries, extra_cols, col_auto, colors=None):
    """Write header rows 1-4."""
    bg_colors, fg_colors = colors if colors else ({}, {})

    def _apply_cell_colors(r, c):
        """Apply bg/fg colors to a cell at (r, c)."""
        bg = bg_colors.get(c)
        fg = fg_colors.get(c)
        if bg:
            ws.cell(r, c).fill = _make_header_fill(bg)
        if fg:
            ws.cell(r, c).font = _make_header_font(fg)

    for entry in header_entries:
        parsed = _parse_merge_range(entry.merge_str)
        if not parsed:
            continue
        min_col, min_row, max_col, max_row = parsed

        font = HEADER_FONT
        fill = None
        fg = fg_colors.get(min_col)
        bg = bg_colors.get(min_col)
        if fg:
            font = _make_header_font(fg)
        if bg:
            fill = _make_header_fill(bg)

        _set_cell(ws, min_row, min_col, entry.text, font=font,
                  fill=fill, alignment=CENTER_WRAP, border=THIN_BORDER)

        if min_col != max_col or min_row != max_row:
            ws.merge_cells(
                start_row=min_row, start_column=min_col,
                end_row=max_row, end_column=max_col,
            )
            for r in range(min_row, max_row + 1):
                for c in range(min_col, max_col + 1):
                    if r != min_row or c != min_col:
                        ws.cell(r, c).border = THIN_BORDER
                        ws.cell(r, c).alignment = CENTER_WRAP
                        _apply_cell_colors(r, c)

    # Write extra column headers (CAN etc.)
    for col_str, col_name, merge_str in extra_cols:
        parsed = _parse_merge_range(merge_str)
        if not parsed:
            continue
        min_col, min_row, max_col, max_row = parsed
        bg = bg_colors.get(min_col)
        fill = _make_header_fill(bg) if bg else None
        _set_cell(ws, min_row, min_col, col_name, font=HEADER_FONT,
                  fill=fill, alignment=CENTER_WRAP, border=THIN_BORDER)
        if min_col != max_col or min_row != max_row:
            ws.merge_cells(start_row=min_row, start_column=min_col,
                           end_row=max_row, end_column=max_col)
            for r in range(min_row, max_row + 1):
                for c in range(min_col, max_col + 1):
                    if r != min_row or c != min_col:
                        ws.cell(r, c).border = THIN_BORDER
                        ws.cell(r, c).font = HEADER_FONT

    # Write auto column header
    if col_auto:
        bg = bg_colors.get(col_auto)
        fill = _make_header_fill(bg) if bg else None
        fg = fg_colors.get(col_auto)
        font = _make_header_font(fg) if fg else HEADER_FONT
        _set_cell(ws, 2, col_auto, "仕様番号自動生成計算式（隠し列）",
                  font=font, fill=fill, alignment=CENTER_WRAP, border=THIN_BORDER)
        ws.merge_cells(start_row=2, start_column=col_auto,
                       end_row=4, end_column=col_auto)

    # Set column A/B colors for rows 1-4
    for r in range(1, 5):
        for c in [1, 2]:
            _apply_cell_colors(r, c)


def _shift_header_entries(base_entries, num_extras):
    """Shift header entries that are after column L (12) by num_extras positions."""
    shifted = []
    for entry in base_entries:
        parsed = _parse_merge_range(entry.merge_str)
        if not parsed:
            shifted.append(entry)
            continue
        min_col, min_row, max_col, max_row = parsed

        if min_col > 12:
            # Shift right by num_extras
            new_min = min_col + num_extras
            new_max = max_col + num_extras
            new_min_letter = get_column_letter(new_min)
            new_max_letter = get_column_letter(new_max)
            new_col_str = new_min_letter if new_min == new_max else f"{new_min_letter}-{new_max_letter}"
            new_merge = f"{new_min_letter}{min_row}:{new_max_letter}{max_row}"
            shifted.append(HeaderEntry(col_str=new_col_str, text=entry.text, merge_str=new_merge))
        else:
            shifted.append(entry)
    return shifted


def write_component_rows(ws, comp, config):
    """Write rows 5-7 (component u/o/o)."""
    auto_col = config.get("col_auto")

    # Row 5: u
    _set_cell(ws, 5, 2, "u", border=NO_BORDER)
    _set_cell(ws, 5, 3, comp.doc_id, fill=BLUE_FILL, alignment=CENTER_TOP)
    _set_cell(ws, 5, 4, comp.info, fill=YELLOW_FILL)
    ws.merge_cells(start_row=5, start_column=4, end_row=5, end_column=10)
    _set_cell(ws, 5, config["col_spec_id"], _unescape_spec_newlines(comp.spec_id), alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, 5, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, 5, config)
    if auto_col:
        _set_cell(ws, 5, auto_col, _spec_id_auto(comp.spec_id), border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)

    # Row 6: o (理由)
    _set_cell(ws, 6, 2, "o", border=NO_BORDER)
    _set_cell(ws, 6, 3, "理由", alignment=CENTER_CENTER)
    reason_text = comp.reason if comp.reason else "記載無し"
    _set_cell(ws, 6, 4, reason_text)
    ws.merge_cells(start_row=6, start_column=4, end_row=6, end_column=10)
    _set_cell(ws, 6, config["col_spec_id"], "-", alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, 6, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, 6, config)
    if auto_col:
        _set_cell(ws, 6, auto_col, "＜理由＞", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)

    # Row 7: o (説明)
    _set_cell(ws, 7, 2, "o", border=NO_BORDER)
    _set_cell(ws, 7, 3, "説明", alignment=CENTER_CENTER)
    explanation_text = comp.explanation if comp.explanation else "記載無し"
    _set_cell(ws, 7, 4, explanation_text)
    ws.merge_cells(start_row=7, start_column=4, end_row=7, end_column=10)
    _set_cell(ws, 7, config["col_spec_id"], "-", alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, 7, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, 7, config)
    if auto_col:
        _set_cell(ws, 7, auto_col, "＜説明＞", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)


def write_separator_row(ws, sep_label, config):
    """Write row 8 (separator)."""
    auto_col = config.get("col_auto")

    _set_cell(ws, 8, 2, "", border=NO_BORDER)
    _set_cell(ws, 8, 3, sep_label, font=WHITE_FONT, fill=DARK_GRAY_FILL,
              border=BORDER_SPAN_LEFT)
    for col in range(4, 11):
        _set_cell(ws, 8, col, "", font=WHITE_FONT, fill=DARK_GRAY_FILL,
                  border=BORDER_SPAN_MID if col < 10 else BORDER_SPAN_RIGHT)
    ws.merge_cells(start_row=8, start_column=3, end_row=8, end_column=10)
    _set_cell(ws, 8, config["col_spec_id"], "", border=THIN_BORDER)
    _set_cell(ws, 8, config["col_usdm_ref"], "", border=THIN_BORDER, alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, 8, config)
    if auto_col:
        # Category from sheet name
        _set_cell(ws, 8, auto_col, sep_label, border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)


def write_t_row(ws, row, section_name, config):
    auto_col = config.get("col_auto")
    last_col = auto_col if auto_col else config["col_usdm_ref"]

    _set_cell(ws, row, 2, "t", border=NO_BORDER)
    _set_cell(ws, row, 3, section_name, fill=GRAY_FILL, border=BORDER_SPAN_LEFT, alignment=NOWRAP_ALIGNMENT)
    for col in range(4, last_col):
        _set_cell(ws, row, col, "", fill=GRAY_FILL, border=BORDER_SPAN_MID)
    _set_cell(ws, row, last_col, "", fill=GRAY_FILL, border=BORDER_SPAN_RIGHT)
    _set_outline_level(ws, row, 0)
    return row + 1


def write_tt_top_row(ws, row, section_name, config):
    _set_cell(ws, row, 2, "tt", border=NO_BORDER)
    _set_cell(ws, row, 3, section_name)
    ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=12)
    _fill_gap_borders(ws, row, config)
    auto_col = config.get("col_auto")
    if auto_col:
        _set_cell(ws, row, auto_col, "", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, section_name)
    _set_outline_level(ws, row, 0)
    return row + 1


def write_u_row(ws, row, u, config, outline_level=1):
    auto_col = config.get("col_auto")
    value, font = md_to_cell(u.text)

    _set_cell(ws, row, 2, "u", border=NO_BORDER)
    _set_cell(ws, row, 3, "要件", fill=BLUE_FILL, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, _unescape_spec_newlines(u.req_id), font=font, alignment=CENTER_TOP)
    _set_cell(ws, row, 5, value, font=font, fill=YELLOW_FILL)
    ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=10)
    _set_cell(ws, row, config["col_spec_id"], _unescape_spec_newlines(u.spec_id), alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, row, config)
    if auto_col:
        _set_cell(ws, row, auto_col, _spec_id_auto(u.spec_id), border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level)
    row += 1

    # o: 理由
    _set_cell(ws, row, 2, "o", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_TOP, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "理由", alignment=CENTER_CENTER)
    if u.reason:
        value, font = md_to_cell(u.reason)
        _set_cell(ws, row, 5, value, font=font)
    else:
        value = "記載無し"
        _set_cell(ws, row, 5, value)
    ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=10)
    _set_cell(ws, row, config["col_spec_id"], "-", alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, row, config)
    if auto_col:
        _set_cell(ws, row, auto_col, "＜理由＞", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level + 1)
    row += 1

    # o: 説明
    _set_cell(ws, row, 2, "o", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "説明", alignment=CENTER_CENTER)
    if u.explanation:
        value, font = md_to_cell(u.explanation)
        _set_cell(ws, row, 5, value, font=font)
    else:
        value = "記載無し"
        _set_cell(ws, row, 5, value)
    ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=10)
    _set_cell(ws, row, config["col_spec_id"], "-", alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, row, config)
    if auto_col:
        _set_cell(ws, row, auto_col, "＜説明＞", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level + 1)
    row += 1

    return row


def write_uu_block(ws, row, uu, config, outline_level=2):
    auto_col = config.get("col_auto")
    value, font = md_to_cell(uu.text)

    _set_cell(ws, row, 2, "uu", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "要件", fill=BLUE_FILL, alignment=CENTER_TOP)
    _set_cell(ws, row, 5, _unescape_spec_newlines(uu.req_id), font=font, alignment=CENTER_TOP)
    _set_cell(ws, row, 6, value, font=font, fill=YELLOW_FILL)
    ws.merge_cells(start_row=row, start_column=6, end_row=row, end_column=10)
    _set_cell(ws, row, config["col_spec_id"], _unescape_spec_newlines(uu.spec_id), alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, row, config)
    if auto_col:
        _set_cell(ws, row, auto_col, _spec_id_auto(uu.spec_id), border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level)
    row += 1

    # oo: 理由
    _set_cell(ws, row, 2, "oo", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "", border=BORDER_VERT_TOP, alignment=CENTER_TOP)
    _set_cell(ws, row, 5, "理由", alignment=CENTER_CENTER)
    if uu.reason:
        value, font = md_to_cell(uu.reason)
        _set_cell(ws, row, 6, value, font=font)
    else:
        value = "記載無し"
        _set_cell(ws, row, 6, value)
    ws.merge_cells(start_row=row, start_column=6, end_row=row, end_column=10)
    _set_cell(ws, row, config["col_spec_id"], "-", alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, row, config)
    if auto_col:
        _set_cell(ws, row, auto_col, "＜理由＞", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level + 1)
    row += 1

    # oo: 説明
    _set_cell(ws, row, 2, "oo", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 5, "説明", alignment=CENTER_CENTER)
    if uu.explanation:
        value, font = md_to_cell(uu.explanation)
        _set_cell(ws, row, 6, value, font=font)
    else:
        value = "記載無し"
        _set_cell(ws, row, 6, value)
    ws.merge_cells(start_row=row, start_column=6, end_row=row, end_column=10)
    _set_cell(ws, row, config["col_spec_id"], "-", alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], "", alignment=NOWRAP_ALIGNMENT)
    _fill_gap_borders(ws, row, config)
    if auto_col:
        _set_cell(ws, row, auto_col, "＜説明＞", border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)
    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level + 1)
    row += 1

    # All specs (including former hw specs)
    for spec in uu.specs:
        row = write_ss_row(ws, row, spec, config, outline_level + 1)

    for tt in uu.subsections:
        row = write_tt_subsection(ws, row, tt, config, outline_level + 1)

    return row


def write_ss_row(ws, row, spec, config, outline_level=2):
    _set_cell(ws, row, 2, "ss", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 5, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 6, spec.ss_type, fill=ORANGE_FILL, alignment=CENTER_TOP)
    _set_cell(ws, row, 7, spec.number, alignment=CENTER_TOP)
    ws.merge_cells(start_row=row, start_column=7, end_row=row, end_column=9)

    value, font = md_to_cell(spec.content)
    _set_cell(ws, row, config["col_content"], value, font=font)
    _set_cell(ws, row, config["col_spec_id"], _unescape_spec_newlines(spec.spec_id), alignment=NOWRAP_ALIGNMENT)
    _set_cell(ws, row, config["col_usdm_ref"], spec.usdm_ref if spec.usdm_ref else "", alignment=NOWRAP_ALIGNMENT)

    # Extra columns
    for col_str, col_name, _ in config.get("header_extra_cols", []):
        col_letter = col_str.split("-")[0]
        col_num = column_index_from_string(col_letter)
        val = spec.extras.get(col_name, "")
        _set_cell(ws, row, col_num, val or "")

    _fill_gap_borders(ws, row, config)

    auto_col = config.get("col_auto")
    if auto_col:
        _set_cell(ws, row, auto_col, _spec_id_auto(spec.spec_id), border=BORDER_AUTO_COL, alignment=NOWRAP_ALIGNMENT)

    _adjust_row_height(ws, row, value)
    _set_outline_level(ws, row, outline_level)
    return row + 1


def write_tt_subsection(ws, row, tt, config, outline_level=2):
    _set_cell(ws, row, 2, "tt", border=NO_BORDER)
    _set_cell(ws, row, 3, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 4, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)
    _set_cell(ws, row, 5, "", border=BORDER_VERT_ONLY, alignment=CENTER_TOP)

    last_col = config.get("col_auto", config["col_usdm_ref"])
    _set_cell(ws, row, 6, tt.name, border=BORDER_SPAN_LEFT, alignment=NOWRAP_ALIGNMENT)
    for c in range(7, last_col):
        _set_cell(ws, row, c, "", border=BORDER_SPAN_MID)
    _set_cell(ws, row, last_col, "", border=BORDER_SPAN_RIGHT)

    _set_outline_level(ws, row, outline_level)
    row += 1

    for spec in tt.specs:
        row = write_ss_row(ws, row, spec, config, outline_level)

    return row


def _set_column_widths(ws, config):
    """Set column widths from config (read from Markdown metadata)."""
    col_widths = config.get("col_widths", {})
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width


def _shift_colors(base_colors, num_extras):
    """Shift color dicts for sheets with extra columns (columns > 12 shift right)."""
    bg_colors, fg_colors = base_colors
    shifted_bg = {}
    shifted_fg = {}
    for col_idx, color in bg_colors.items():
        if col_idx > 12:
            shifted_bg[col_idx + num_extras] = color
        else:
            shifted_bg[col_idx] = color
    for col_idx, color in fg_colors.items():
        if col_idx > 12:
            shifted_fg[col_idx + num_extras] = color
        else:
            shifted_fg[col_idx] = color
    return (shifted_bg, shifted_fg)


# ---------------------------------------------------------------------------
# Template Format Write Functions
# ---------------------------------------------------------------------------

HCENTER_VCENTER = Alignment(horizontal='center', vertical='center', wrap_text=False)


def _tmpl_set(ws, row, col, value, font=None, fill=None, alignment=None):
    """Set cell value with optional font/fill/alignment for template format."""
    cell = ws.cell(row, col)
    cell.value = value
    cell.font = font or DEFAULT_FONT
    cell.border = THIN_BORDER
    cell.alignment = alignment or WRAP_ALIGNMENT
    if fill:
        cell.fill = fill


def write_template_header(ws, header_entries, last_col):
    """Write single-row header (row 1) for template format."""
    for entry in header_entries:
        parsed = _parse_merge_range(entry.merge_str)
        if not parsed:
            continue
        min_col, min_row, max_col, max_row = parsed
        _set_cell(ws, 1, min_col, entry.text, font=HEADER_FONT,
                  alignment=CENTER_WRAP, border=THIN_BORDER)
        if min_col != max_col:
            ws.merge_cells(start_row=1, start_column=min_col,
                           end_row=1, end_column=max_col)
            for c in range(min_col + 1, max_col + 1):
                ws.cell(1, c).border = THIN_BORDER


def write_template_u_row(ws, row, u, col_u, last_col, section_name=""):
    """Write u + o + o rows for template format."""
    value, font = md_to_cell(u.text)

    # u row
    _tmpl_set(ws, row, 1, section_name, fill=TMPL_U_FILL)
    _tmpl_set(ws, row, col_u, "要求", fill=TMPL_U_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_u + 1, u.req_id, font=font, fill=TMPL_U_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_u + 2, value, font=font, fill=TMPL_U_FILL)
    if col_u + 2 < last_col:
        for c in range(col_u + 3, last_col + 1):
            _tmpl_set(ws, row, c, "", fill=TMPL_U_FILL)
        ws.merge_cells(start_row=row, start_column=col_u + 2,
                       end_row=row, end_column=last_col)
    ws.row_dimensions[row].outline_level = 0
    row += 1

    # o: 理由
    reason = u.reason or "記載無し"
    r_value, r_font = md_to_cell(reason)
    _tmpl_set(ws, row, 1, "", fill=TMPL_U_FILL)
    _tmpl_set(ws, row, col_u, "", fill=TMPL_U_FILL)
    _tmpl_set(ws, row, col_u + 1, "理由", fill=TMPL_U_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_u + 2, r_value, font=r_font, fill=TMPL_U_FILL)
    if col_u + 2 < last_col:
        for c in range(col_u + 3, last_col + 1):
            _tmpl_set(ws, row, c, "", fill=TMPL_U_FILL)
        ws.merge_cells(start_row=row, start_column=col_u + 2,
                       end_row=row, end_column=last_col)
    ws.row_dimensions[row].outline_level = 1
    row += 1

    # o: 説明
    expl = u.explanation or "記載無し"
    e_value, e_font = md_to_cell(expl)
    _tmpl_set(ws, row, 1, "", fill=TMPL_U_FILL)
    _tmpl_set(ws, row, col_u, "", fill=TMPL_U_FILL)
    _tmpl_set(ws, row, col_u + 1, "説明", fill=TMPL_U_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_u + 2, e_value, font=e_font, fill=TMPL_U_FILL)
    if col_u + 2 < last_col:
        for c in range(col_u + 3, last_col + 1):
            _tmpl_set(ws, row, c, "", fill=TMPL_U_FILL)
        ws.merge_cells(start_row=row, start_column=col_u + 2,
                       end_row=row, end_column=last_col)
    ws.row_dimensions[row].outline_level = 1
    row += 1

    return row


def write_template_uu_block(ws, row, uu, col_uu, last_col):
    """Write uu + oo + oo + ss rows for template format."""
    value, font = md_to_cell(uu.text)

    # uu row
    _tmpl_set(ws, row, 1, "")
    for c in range(2, col_uu):
        _tmpl_set(ws, row, c, "")
    _tmpl_set(ws, row, col_uu, "要求", fill=TMPL_UU_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_uu + 1, uu.req_id, font=font, fill=TMPL_UU_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_uu + 2, value, font=font, fill=TMPL_UU_FILL)
    ws.row_dimensions[row].outline_level = 1
    row += 1

    # oo: 理由
    reason = uu.reason or "記載無し"
    r_value, r_font = md_to_cell(reason)
    _tmpl_set(ws, row, 1, "")
    for c in range(2, col_uu):
        _tmpl_set(ws, row, c, "")
    _tmpl_set(ws, row, col_uu, "", fill=TMPL_UU_FILL)
    _tmpl_set(ws, row, col_uu + 1, "理由", fill=TMPL_UU_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_uu + 2, r_value, font=r_font, fill=TMPL_UU_FILL)
    ws.row_dimensions[row].outline_level = 2
    row += 1

    # oo: 説明
    expl = uu.explanation or "記載無し"
    e_value, e_font = md_to_cell(expl)
    _tmpl_set(ws, row, 1, "")
    for c in range(2, col_uu):
        _tmpl_set(ws, row, c, "")
    _tmpl_set(ws, row, col_uu, "", fill=TMPL_UU_FILL)
    _tmpl_set(ws, row, col_uu + 1, "説明", fill=TMPL_UU_FILL, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_uu + 2, e_value, font=e_font, fill=TMPL_UU_FILL)
    ws.row_dimensions[row].outline_level = 2
    row += 1

    # Specs
    for spec in uu.specs:
        row = write_template_ss_row(ws, row, spec, col_uu)

    # tt subsections
    for tt in uu.subsections:
        _tmpl_set(ws, row, 1, "")
        for c in range(2, col_uu):
            _tmpl_set(ws, row, c, "")
        _tmpl_set(ws, row, col_uu, "")
        _tmpl_set(ws, row, col_uu + 1, tt.name)
        if col_uu + 2 <= last_col:
            _tmpl_set(ws, row, col_uu + 2, "")
        ws.row_dimensions[row].outline_level = 2
        row += 1
        for spec in tt.specs:
            row = write_template_ss_row(ws, row, spec, col_uu)

    return row


def write_template_ss_row(ws, row, spec, col_uu):
    """Write ss row for template format."""
    value, font = md_to_cell(spec.content)
    _tmpl_set(ws, row, 1, "")
    for c in range(2, col_uu):
        _tmpl_set(ws, row, c, "")
    _tmpl_set(ws, row, col_uu, spec.ss_type, alignment=HCENTER_VCENTER)
    _tmpl_set(ws, row, col_uu + 1, spec.spec_id)
    _tmpl_set(ws, row, col_uu + 2, value, font=font)
    ws.row_dimensions[row].outline_level = 2
    return row + 1


def write_template_sheet(ws, sheet_data, config, header_entries):
    """Write a complete sheet in template format (no component/separator rows)."""
    col_u = config["col_u_start"]
    col_uu = config["col_uu_start"]
    last_col = config["last_data_col"]

    # Header row 1
    write_template_header(ws, header_entries, last_col)

    # Column widths
    _set_column_widths(ws, config)

    # Outline
    ws.sheet_properties.outlinePr = Outline(summaryBelow=True, summaryRight=True)

    # Data rows from row 2
    row = 2
    has_sections = config["has_sections"]

    if has_sections:
        for section in sheet_data.sections:
            for u in section.upper_reqs:
                row = write_template_u_row(ws, row, u, col_u, last_col, section.name)
                for uu in u.lower_reqs:
                    row = write_template_uu_block(ws, row, uu, col_uu, last_col)
    else:
        for u in sheet_data.upper_reqs:
            row = write_template_u_row(ws, row, u, col_u, last_col)
            for uu in u.lower_reqs:
                row = write_template_uu_block(ws, row, uu, col_uu, last_col)

    # Auto-filter
    last_col_letter = get_column_letter(last_col)
    ws.auto_filter.ref = f"A1:{last_col_letter}{max(row - 1, 1)}"

    return row - 2


# ---------------------------------------------------------------------------
# 19-column Format Write Functions
# ---------------------------------------------------------------------------

def write_sheet(ws, sheet_data, config, base_header_entries, comp, base_colors=None):
    """Write all rows for one sheet (rows 1-8 + data rows 9+)."""
    num_extras = len(config.get("header_extra_cols", []))
    extra_cols = config.get("header_extra_cols", [])
    col_auto = config.get("col_auto")

    # Shift header entries and colors if this sheet has extra columns
    if num_extras > 0:
        shifted_entries = _shift_header_entries(base_header_entries, num_extras)
        colors = _shift_colors(base_colors, num_extras) if base_colors else ({}, {})
    else:
        shifted_entries = base_header_entries
        colors = base_colors if base_colors else ({}, {})

    # Merge extra column colors into the colors dict
    extra_col_colors = config.get("extra_col_colors", ({}, {}))
    if extra_col_colors != ({}, {}):
        bg, fg = colors
        ebg, efg = extra_col_colors
        bg = dict(bg)
        fg = dict(fg)
        bg.update(ebg)
        fg.update(efg)
        colors = (bg, fg)

    # Write header rows 1-4
    write_header_rows(ws, shifted_entries, extra_cols, col_auto, colors)

    # Write component rows 5-7
    # Build per-sheet component (with possible overrides)
    sheet_comp = ComponentInfo(
        doc_id=comp.doc_id, spec_id=comp.spec_id,
        info=comp.info,
        reason=sheet_data.component_reason,
        explanation=sheet_data.component_explanation,
    )
    write_component_rows(ws, sheet_comp, config)

    # Write separator row 8
    write_separator_row(ws, sheet_data.separator_label, config)

    # Set column widths
    _set_column_widths(ws, config)

    # Set outline properties
    ws.sheet_properties.outlinePr = Outline(summaryBelow=True, summaryRight=True)

    # Write data rows 9+
    row = 9
    has_sections = config["has_sections"]
    section_marker = config["section_marker"]

    def _add_bottom_border(ws, row_num, cols):
        for c in cols:
            cell = ws.cell(row_num, c)
            old = cell.border
            cell.border = Border(
                left=old.left, right=old.right, top=old.top,
                bottom=Side(style='thin'),
            )

    if has_sections:
        for section in sheet_data.sections:
            if section_marker == "t":
                row = write_t_row(ws, row, section.name, config)
            elif section_marker == "tt":
                row = write_tt_top_row(ws, row, section.name, config)
            for u in section.upper_reqs:
                row = write_u_row(ws, row, u, config, outline_level=1)
                for uu in u.lower_reqs:
                    row = write_uu_block(ws, row, uu, config)
                _add_bottom_border(ws, row - 1, [3, 4, 5])
    else:
        for u in sheet_data.upper_reqs:
            row = write_u_row(ws, row, u, config, outline_level=0)
            for uu in u.lower_reqs:
                row = write_uu_block(ws, row, uu, config, outline_level=1)
            _add_bottom_border(ws, row - 1, [3, 4, 5])

    # Auto-filter on header row 4
    last_col = col_auto if col_auto else config["col_usdm_ref"]
    last_col_letter = get_column_letter(last_col)
    ws.auto_filter.ref = f"A1:{last_col_letter}{row - 1}"

    return row - 9


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def count_by_type(sheet_data):
    counts = {"t": 0, "u": 0, "uu": 0, "ss": 0, "tt": 0, "o": 0, "oo": 0}
    all_u = list(sheet_data.upper_reqs)
    counts["t"] = len(sheet_data.sections)
    for sec in sheet_data.sections:
        all_u.extend(sec.upper_reqs)
    counts["u"] = len(all_u)
    counts["o"] = len(all_u) * 2
    for u in all_u:
        counts["uu"] += len(u.lower_reqs)
        counts["oo"] += len(u.lower_reqs) * 2
        for uu in u.lower_reqs:
            counts["ss"] += len(uu.specs)
            counts["tt"] += len(uu.subsections)
            for tt in uu.subsections:
                counts["ss"] += len(tt.specs)
    return counts


# ---------------------------------------------------------------------------
# XLSX Post-processor
# ---------------------------------------------------------------------------

def _fix_xlsx_cell_types(xlsx_path):
    """Fix openpyxl XLSX output for Excel compatibility.

    openpyxl 3.1.x writes all strings as inline strings (t="inlineStr")
    and empty cells as t="n".  Excel triggers a repair dialog for these.
    This post-processor:
      1. Removes t="n" from empty cells (no <v> element).
      2. Converts all inline strings to shared strings — moves <is> content
         into xl/sharedStrings.xml and replaces cells with t="s" + <v>index</v>.
    """
    import zipfile
    import shutil
    import xml.etree.ElementTree as ET

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ns_r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    ns_ct = 'http://schemas.openxmlformats.org/package/2006/content-types'
    ns_pr = 'http://schemas.openxmlformats.org/package/2006/relationships'
    ET.register_namespace('', ns)
    ET.register_namespace('r', ns_r)

    # --- Pass 1: collect all inline strings across all sheets ---
    shared_strings = []       # ordered list of <si> XML strings
    shared_map = {}           # is_xml_key -> index
    sheet_data = {}           # filename -> modified ET root
    total_refs = 0            # total cell references to shared strings

    with zipfile.ZipFile(xlsx_path, 'r') as zf:
        all_items = zf.infolist()
        for item in all_items:
            if not (item.filename.startswith('xl/worksheets/sheet') and
                    item.filename.endswith('.xml')):
                continue
            tree = ET.parse(zf.open(item.filename))
            root = tree.getroot()
            for c in root.iter(f'{{{ns}}}c'):
                t_attr = c.get('t')
                # Fix empty cells
                if t_attr == 'n':
                    v = c.find(f'{{{ns}}}v')
                    if v is None:
                        del c.attrib['t']
                # Convert inlineStr to shared string
                if t_attr == 'inlineStr':
                    is_elem = c.find(f'{{{ns}}}is')
                    if is_elem is None:
                        # Empty inlineStr (no <is> child) — treat as empty cell
                        del c.attrib['t']
                    else:
                        # Use the XML of <is> content as the dedup key
                        is_key = ET.tostring(is_elem, encoding='unicode')
                        if is_key not in shared_map:
                            shared_map[is_key] = len(shared_strings)
                            # Build <si> element (same children as <is>)
                            shared_strings.append(is_key)
                        idx = shared_map[is_key]
                        # Replace cell: t="s", <v>idx</v>, remove <is>
                        c.set('t', 's')
                        c.remove(is_elem)
                        v_elem = ET.SubElement(c, f'{{{ns}}}v')
                        v_elem.text = str(idx)
                        total_refs += 1
            sheet_data[item.filename] = root

    if not shared_strings:
        return

    # --- Build sharedStrings.xml ---
    ns_xml = 'http://www.w3.org/XML/1998/namespace'
    sst = ET.Element(f'{{{ns}}}sst')
    sst.set('count', str(total_refs))
    sst.set('uniqueCount', str(len(shared_strings)))

    # Boolean property tags in CT_RPrElt — val="1" should be bare element
    _bool_tags = frozenset(['b', 'i', 'strike', 'outline', 'shadow',
                            'condense', 'extend'])

    for is_xml in shared_strings:
        si = ET.SubElement(sst, f'{{{ns}}}si')
        is_elem = ET.fromstring(is_xml)
        # Copy children of <is> into <si>
        for child in is_elem:
            si.append(child)
        # Also copy text/tail if <is> has direct text (plain <t>)
        if is_elem.text:
            si.text = is_elem.text

    # --- Fix boolean properties and xml:space in shared strings ---
    for si in sst:
        # Fix boolean properties: <strike val="1"/> → <strike/>
        for rpr in si.iter(f'{{{ns}}}rPr'):
            for tag_name in _bool_tags:
                for elem in rpr.findall(f'{{{ns}}}{tag_name}'):
                    val = elem.get('val')
                    if val in ('1', 'true'):
                        del elem.attrib['val']
        # Add xml:space="preserve" to <t> elements with significant whitespace
        for t_elem in si.iter(f'{{{ns}}}t'):
            text = t_elem.text or ''
            if text != text.strip() or '\n' in text or '\t' in text:
                t_elem.set(f'{{{ns_xml}}}space', 'preserve')

    sst_xml = ET.tostring(sst, encoding='unicode', xml_declaration=True).encode('utf-8')

    # --- Pass 2: rewrite the zip ---
    tmp_path = xlsx_path + '.tmp'
    sst_path = 'xl/sharedStrings.xml'
    sst_added = False

    with zipfile.ZipFile(xlsx_path, 'r') as zin, \
         zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename in sheet_data:
                data = ET.tostring(sheet_data[item.filename],
                                   encoding='unicode',
                                   xml_declaration=True).encode('utf-8')
                zout.writestr(item, data)

            elif item.filename == '[Content_Types].xml':
                # Add sharedStrings content type
                ct_tree = ET.parse(zin.open(item.filename))
                ct_root = ct_tree.getroot()
                # Check if already present
                found = False
                for ov in ct_root.findall(f'{{{ns_ct}}}Override'):
                    if ov.get('PartName') == '/xl/sharedStrings.xml':
                        found = True
                        break
                if not found:
                    ET.register_namespace('', ns_ct)
                    ov_new = ET.SubElement(ct_root, f'{{{ns_ct}}}Override')
                    ov_new.set('PartName', '/xl/sharedStrings.xml')
                    ov_new.set('ContentType',
                               'application/vnd.openxmlformats-officedocument'
                               '.spreadsheetml.sharedStrings+xml')
                data = ET.tostring(ct_root, encoding='unicode',
                                   xml_declaration=True).encode('utf-8')
                zout.writestr(item, data)

            elif item.filename == 'xl/_rels/workbook.xml.rels':
                # Add relationship to sharedStrings
                ET.register_namespace('', ns_pr)
                rels_tree = ET.parse(zin.open(item.filename))
                rels_root = rels_tree.getroot()
                found = False
                max_id = 0
                for rel in rels_root:
                    rid = rel.get('Id', '')
                    if rid.startswith('rId'):
                        try:
                            max_id = max(max_id, int(rid[3:]))
                        except ValueError:
                            pass
                    if 'sharedStrings' in rel.get('Target', ''):
                        found = True
                if not found:
                    new_rel = ET.SubElement(rels_root, f'{{{ns_pr}}}Relationship')
                    new_rel.set('Id', f'rId{max_id + 1}')
                    new_rel.set('Type',
                                'http://schemas.openxmlformats.org/officeDocument'
                                '/2006/relationships/sharedStrings')
                    new_rel.set('Target', 'sharedStrings.xml')
                data = ET.tostring(rels_root, encoding='unicode',
                                   xml_declaration=True).encode('utf-8')
                zout.writestr(item, data)
            else:
                zout.writestr(item, zin.read(item.filename))

            if item.filename == sst_path:
                sst_added = True

        # Write sharedStrings.xml
        if not sst_added:
            zout.writestr(sst_path, sst_xml)

    shutil.move(tmp_path, xlsx_path)
    print(f"  Post-process: {len(shared_strings)} unique / {total_refs} total shared strings")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 md2usdm.py <md_dir> [output.xlsx]")
        sys.exit(1)

    md_dir = sys.argv[1]

    # Parse top-level index
    top_index_path = os.path.join(md_dir, "index.md")
    header_entries, sheet_list, excel_basename, base_col_widths, base_colors, col_markers = parse_top_index(top_index_path)

    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    else:
        output_path = os.path.join(md_dir, f"{excel_basename}.xlsx")

    print(f"=== Markdown → Excel USDM 逆変換 ===")
    print(f"  Markdown dir: {md_dir}/")
    print(f"  Output:       {output_path}")
    print()
    print(f"Found {len(sheet_list)} sheets in index.md")
    print(f"Header entries: {len(header_entries)}, base column widths: {len(base_col_widths)}")

    # Find and parse component file
    # Look for *.md files in the root that are not index.md
    comp = None
    for f in os.listdir(md_dir):
        if f.endswith(".md") and f != "index.md":
            comp_path = os.path.join(md_dir, f)
            comp = parse_component_file(comp_path)
            print(f"Component file: {f} (doc_id={comp.doc_id})")
            break

    if comp is None:
        print("ERROR: No component file found!")
        sys.exit(1)

    # Parse all sheets
    print("\nParsing Markdown files...")
    parsed_sheets = []
    for sheet_name, dir_name in sheet_list:
        print(f"  Parsing: {sheet_name} ({dir_name}/)")
        sheet_data = parse_sheet_index(md_dir, dir_name, sheet_name, comp, base_col_widths)
        parsed_sheets.append(sheet_data)

    # Verification
    print("\n" + "=" * 60)
    print("パース検証")
    print("=" * 60)
    for sheet_data in parsed_sheets:
        counts = count_by_type(sheet_data)
        total = sum(counts.values())
        print(f"  [{sheet_data.sheet_name}]")
        print(f"    t:{counts['t']:4d}  u:{counts['u']:4d}  uu:{counts['uu']:4d}  ss:{counts['ss']:4d}  tt:{counts['tt']:4d}  total:{total}")

    # Create new workbook
    print(f"\nCreating new workbook...")
    wb = openpyxl.Workbook()

    # Remove default sheet
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Detect template format from col_markers
    is_template = 'bold' in col_markers and 'code' not in col_markers
    if is_template:
        col_u_start = column_index_from_string(col_markers['bold'])
        col_uu_start = column_index_from_string(col_markers.get('strike', col_markers['bold']))
        last_data_col = len(base_col_widths)
        print(f"Format: template (col_u={col_markers['bold']}, col_uu={col_markers.get('strike', col_markers['bold'])}, cols={last_data_col})")

    # Write each sheet
    print("Writing Excel data...")
    for sheet_data in parsed_sheets:
        config = sheet_data.config
        ws = wb.create_sheet(title=sheet_data.sheet_name)
        if is_template:
            config["col_u_start"] = col_u_start
            config["col_uu_start"] = col_uu_start
            config["last_data_col"] = last_data_col
            rows_written = write_template_sheet(ws, sheet_data, config, header_entries)
        else:
            rows_written = write_sheet(ws, sheet_data, config, header_entries, comp, base_colors)
        print(f"  {sheet_data.sheet_name}: {rows_written} data rows written")

    # Set document properties
    wb.properties.title = excel_basename

    # Save
    print(f"\nSaving: {output_path}")
    wb.save(output_path)

    # Post-process: convert inline strings to shared strings, fix empty cell
    # types, and normalize boolean properties for Excel compatibility.
    _fix_xlsx_cell_types(output_path)

    print("Done!")


if __name__ == "__main__":
    main()
