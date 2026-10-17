#!/usr/bin/env python3
"""
Excel USDM → 階層型Markdown 変換スクリプト

Usage:
    python3 usdm2md.py <excel_path> [output_dir]
"""

import errno
import os
import re
import sys
from dataclasses import dataclass, field

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.utils import get_column_letter, column_index_from_string


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Specification:
    """A single ss (specification) row."""
    ss_type: str
    number: str
    content: str
    spec_id: str
    usdm_ref: str
    extras: dict = field(default_factory=dict)


@dataclass
class TtSubsection:
    """A tt subsection within a uu (lower requirement)."""
    name: str
    specs: list = field(default_factory=list)


@dataclass
class LowerReq:
    """A uu (lower requirement)."""
    req_id: str
    text: str
    spec_id: str
    reason: str
    explanation: str
    subsections: list = field(default_factory=list)
    specs: list = field(default_factory=list)


@dataclass
class UpperReq:
    """A u (upper requirement)."""
    req_id: str
    text: str
    spec_id: str
    reason: str
    explanation: str
    lower_reqs: list = field(default_factory=list)


@dataclass
class Section:
    """A t (section header)."""
    number: str
    name: str
    upper_reqs: list = field(default_factory=list)


@dataclass
class SheetData:
    """Parsed data for one Excel sheet."""
    sheet_name: str
    config: dict
    component_info: str
    component_reason: str
    component_explanation: str
    separator_label: str
    sections: list = field(default_factory=list)
    upper_reqs: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Red font detection & formatted text extraction
# ---------------------------------------------------------------------------

def is_red_rgb(rgb_str):
    if not rgb_str:
        return False
    s = str(rgb_str)
    return "FF0000" in s and s.startswith("FF")


def is_red_cell_font(cell):
    try:
        if cell.font and cell.font.color and cell.font.color.rgb:
            return is_red_rgb(cell.font.color.rgb)
    except (AttributeError, TypeError):
        pass
    return False


def is_strike_cell_font(cell):
    try:
        return bool(cell.font and cell.font.strikethrough)
    except (AttributeError, TypeError):
        return False


def is_red_inline_font(font):
    try:
        if font and font.color:
            rgb = font.color.rgb if hasattr(font.color, "rgb") else font.color
            return is_red_rgb(rgb)
    except (AttributeError, TypeError):
        pass
    return False


def is_strike_inline_font(font):
    try:
        return bool(font and font.strike)
    except (AttributeError, TypeError):
        return False


def wrap_format(text, is_red, is_strike):
    if not text.strip():
        return text
    if not is_red and not is_strike:
        return text
    stripped = text.strip()
    leading = text[:len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()):]
    if is_red and is_strike:
        return f"{leading}**~~{stripped}~~**{trailing}"
    if is_red:
        return f"{leading}**{stripped}**{trailing}"
    return f"{leading}~~{stripped}~~{trailing}"


def get_formatted_text(ws_rt, row, col, ws_data=None):
    cell = ws_rt.cell(row, col)
    val = cell.value

    if val is None:
        return ""

    # Formula cells: use the evaluated value from data_only workbook
    if cell.data_type == 'f' and ws_data is not None:
        data_val = ws_data.cell(row, col).value
        if data_val is not None:
            text = str(data_val).strip()
            if text:
                red = is_red_cell_font(cell)
                strike = is_strike_cell_font(cell)
                return wrap_format(text, red, strike)

    if isinstance(val, CellRichText):
        cell_red = is_red_cell_font(cell)
        cell_strike = is_strike_cell_font(cell)
        parts = []
        for part in val:
            if isinstance(part, str):
                parts.append(wrap_format(part, cell_red, cell_strike))
            elif isinstance(part, TextBlock):
                text = str(part)
                red = is_red_inline_font(part.font) if part.font else cell_red
                strike = is_strike_inline_font(part.font) if part.font else cell_strike
                parts.append(wrap_format(text, red, strike))
            else:
                parts.append(str(part))

        result = "".join(parts)
        result = re.sub(r"\*\*\*\*", "", result)
        result = re.sub(r"~~~~", "", result)
        result = re.sub(r"\*\*\s*\*\*", "", result)
        result = re.sub(r"~~\s*~~", "", result)
        return result.strip()

    text = str(val).strip()
    if not text:
        return ""

    red = is_red_cell_font(cell)
    strike = is_strike_cell_font(cell)
    return wrap_format(text, red, strike)


def cell_str(ws, row, col):
    v = ws.cell(row, col).value
    if v is None:
        return ""
    if isinstance(v, CellRichText):
        return str(v).strip()
    return str(v).strip()


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def is_usdm_sheet(ws):
    """Check if worksheet has USDM markers in column B from row 9+."""
    markers = {"t", "tt", "u", "o", "uu", "oo", "ss"}
    for r in range(9, min(ws.max_row + 1, 50)):
        val = cell_str(ws, r, 2)
        if val in markers:
            return True
    return False


def _detect_auto_col(ws_data):
    """Detect the auto-generation formula column by looking for ＜理由＞/＜説明＞ patterns."""
    for col in range(13, min(ws_data.max_column + 1, 30)):
        for r in range(9, min(ws_data.max_row + 1, 50)):
            val = cell_str(ws_data, r, col)
            if val in ("＜理由＞", "＜説明＞"):
                return col
    return None


def _clean_header_text(text):
    """Collapse newlines in header text into a single line."""
    return text.replace("\n", "").replace("\r", "")


def _read_header_text(ws, col):
    """Read the most specific header text for a column from rows 2-4."""
    for r in [4, 3, 2]:
        val = ws.cell(r, col).value
        if val is not None:
            text = str(val).strip()
            if text:
                return _clean_header_text(text)
    return ""


def detect_sheet_config(ws_data, ws_rt, sheet_name, base_auto=None):
    """Auto-detect sheet configuration from Excel content."""
    config = {
        "data_start_row": 9,
        "col_spec_id": 11,   # K
        "col_content": 10,   # J
        "col_usdm_ref": 12,  # L
        "header_extra_cols": [],
    }

    # Detect col_auto
    col_auto = _detect_auto_col(ws_data)
    if col_auto is None:
        col_auto = 18  # fallback to base (R)
    config["col_auto"] = col_auto

    # Detect extra columns between L+1 and the base position
    if base_auto is not None and col_auto > base_auto:
        num_extras = col_auto - base_auto
        # Read full header layout for this sheet to get merge ranges
        sheet_layout = read_header_layout(ws_rt, col_auto)
        # Build lookup: col_letter -> (col_str, text, merge_str)
        layout_by_col = {}
        for col_str, text, merge_str, _w in sheet_layout:
            first_letter = col_str.split("-")[0]
            layout_by_col[first_letter] = (col_str, text, merge_str)
        extras = []
        # Read colors for extra columns
        extra_colors = read_header_colors(ws_rt, col_auto)
        extra_bg, extra_fg = extra_colors
        extra_col_bg = {}
        extra_col_fg = {}
        for col in range(13, 13 + num_extras):
            col_letter = get_column_letter(col)
            if col_letter in layout_by_col:
                col_str, text, merge_str = layout_by_col[col_letter]
                extras.append((col_str, text, merge_str))
            else:
                header = _read_header_text(ws_rt, col)
                extras.append((col_letter, header, f"{col_letter}2:{col_letter}4"))
            if col in extra_bg:
                extra_col_bg[col_letter] = extra_bg[col]
            if col in extra_fg:
                extra_col_fg[col_letter] = extra_fg[col]
        config["header_extra_cols"] = extras
        config["extra_col_colors"] = (extra_col_bg, extra_col_fg)

    # Detect has_sections and section_marker
    has_sections = False
    section_marker = None
    for r in range(9, ws_data.max_row + 1):
        marker = cell_str(ws_data, r, 2)
        if marker == "t":
            c_val = cell_str(ws_data, r, 3)
            if c_val:
                has_sections = True
                section_marker = "t"
                break
        elif marker == "tt":
            c_val = cell_str(ws_data, r, 3)
            if c_val:
                has_sections = True
                section_marker = "tt"
                break
    config["has_sections"] = has_sections
    config["section_marker"] = section_marker

    return config


def read_header_colors(ws, max_col):
    """Read background and font colors for header columns 1..max_col.

    Returns (bg_colors, fg_colors) where each is {col_index: '6-digit hex'}.
    """
    # Build merge origin map for rows 2-4
    origin_map = {}
    for mr in ws.merged_cells.ranges:
        if mr.min_row > 4 or mr.max_row < 2:
            continue
        for r in range(max(mr.min_row, 2), min(mr.max_row, 4) + 1):
            for c in range(mr.min_col, min(mr.max_col, max_col) + 1):
                origin_map[(r, c)] = (mr.min_row, mr.min_col)

    bg_colors = {}
    fg_colors = {}

    for c in range(1, max_col + 1):
        for r in [2, 3]:
            origin = origin_map.get((r, c), (r, c))
            cell = ws.cell(origin[0], origin[1])
            # Background
            if c not in bg_colors:
                try:
                    fill = cell.fill
                    if fill and fill.fill_type == 'solid' and fill.fgColor:
                        rgb = fill.fgColor.rgb
                        if isinstance(rgb, str) and rgb != '00000000':
                            bg_colors[c] = rgb[2:]  # Strip alpha
                except Exception:
                    pass
            # Font color
            if c not in fg_colors:
                try:
                    if cell.font and cell.font.color:
                        color = cell.font.color
                        if color.type == 'rgb' and isinstance(color.rgb, str):
                            rgb = color.rgb
                            if rgb not in ('00000000', 'FF000000'):
                                fg_colors[c] = rgb[2:]
                        elif color.type == 'theme':
                            if color.theme == 0:
                                fg_colors[c] = 'FFFFFF'
                except Exception:
                    pass

    return bg_colors, fg_colors


def read_header_layout(ws, max_col):
    """Read header layout from rows 2-4 up to max_col.

    Returns list of (col_range_str, header_text, merge_range_str).
    """
    entries = []
    covered = set()

    for mr in ws.merged_cells.ranges:
        if mr.min_row > 4 or mr.max_row < 2 or mr.min_row < 2:
            continue
        if mr.min_col > max_col or mr.min_col < 2:
            continue
        actual_max_col = min(mr.max_col, max_col)

        val = ws.cell(mr.min_row, mr.min_col).value
        if val is None:
            continue
        text = _clean_header_text(str(val).strip())
        if not text:
            continue

        min_letter = get_column_letter(mr.min_col)
        max_letter = get_column_letter(actual_max_col)
        col_str = min_letter if mr.min_col == actual_max_col else f"{min_letter}-{max_letter}"
        merge_str = f"{min_letter}{mr.min_row}:{max_letter}{mr.max_row}"

        entries.append((mr.min_col, mr.min_row, col_str, text, merge_str))
        for r in range(mr.min_row, mr.max_row + 1):
            for c in range(mr.min_col, actual_max_col + 1):
                covered.add((r, c))

    # Non-merged cells with values
    for r in range(2, 5):
        for c in range(2, max_col + 1):
            if (r, c) in covered:
                continue
            val = ws.cell(r, c).value
            if val is None:
                continue
            text = _clean_header_text(str(val).strip())
            if not text:
                continue
            col_letter = get_column_letter(c)
            entries.append((c, r, col_letter, text, f"{col_letter}{r}:{col_letter}{r}"))
            covered.add((r, c))

    entries.sort(key=lambda x: (x[0], x[1]))

    # Read column widths for covered columns
    result = []
    for _, _, col_str, text, merge_str in entries:
        first_letter = col_str.split("-")[0]
        col_num = openpyxl.utils.column_index_from_string(first_letter)
        dim = ws.column_dimensions.get(first_letter)
        width = round(dim.width, 2) if dim and dim.width else None
        result.append((col_str, text, merge_str, width))
    return result


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def get_spec_id(ws_data, row, config):
    """Get spec_id from K column, with fallback to auto formula column."""
    val = cell_str(ws_data, row, config["col_spec_id"])
    if val and val != "-":
        return _escape_spec_newlines(val)
    auto_col = config.get("col_auto")
    if auto_col:
        auto_val = cell_str(ws_data, row, auto_col)
        if auto_val and not auto_val.startswith("＜"):
            return _escape_spec_newlines(f"【{auto_val}】")
    return val


def parse_sheet(ws_rt, ws_data, sheet_name, config):
    comp_info = cell_str(ws_rt, 5, 4)
    comp_reason = get_formatted_text(ws_rt, 6, 4, ws_data)
    comp_explanation = get_formatted_text(ws_rt, 7, 4, ws_data)
    sep_label = cell_str(ws_rt, 8, 3)

    # Read column widths — expand col ranges (openpyxl misses min!=max ranges)
    col_widths = {}
    auto_col = config.get("col_auto")
    max_data_col = auto_col if auto_col else 19  # S=19 fallback
    for col_letter, dim in ws_data.column_dimensions.items():
        if dim.width is not None and dim.width > 0:
            col_widths[col_letter] = round(dim.width, 2)
            if dim.min != dim.max:
                limit = min(dim.max, max_data_col)
                for c in range(dim.min, limit + 1):
                    cl = get_column_letter(c)
                    if cl not in col_widths:
                        col_widths[cl] = round(dim.width, 2)
    config["col_widths"] = col_widths

    sheet = SheetData(
        sheet_name=sheet_name,
        config=config,
        component_info=comp_info,
        component_reason=comp_reason,
        component_explanation=comp_explanation,
        separator_label=sep_label,
    )

    start_row = config["data_start_row"]
    has_sections = config["has_sections"]
    section_marker = config["section_marker"]
    extra_cols = config.get("header_extra_cols", [])

    current_section = None
    current_u = None
    current_uu = None
    current_tt = None

    for r in range(start_row, ws_rt.max_row + 1):
        marker = cell_str(ws_rt, r, 2)
        if not marker:
            continue

        # Resolve o/oo ambiguity
        effective_marker = marker
        if marker == "oo":
            d_val = cell_str(ws_rt, r, 4)
            if d_val in ("理由", "説明"):
                effective_marker = "o"
        elif marker == "o":
            e_val = cell_str(ws_rt, r, 5)
            d_val = cell_str(ws_rt, r, 4)
            if e_val in ("理由", "説明") and d_val not in ("理由", "説明"):
                effective_marker = "oo"

        # Section header (t)
        if marker == "t" and has_sections and section_marker == "t":
            name = cell_str(ws_rt, r, 3)
            num = name.split(".")[0] if "." in name else name
            current_section = Section(number=num, name=name)
            sheet.sections.append(current_section)
            current_u = None
            current_uu = None
            current_tt = None
            continue

        # Top-level tt (section-like)
        if marker == "tt" and has_sections and section_marker == "tt":
            c_val = cell_str(ws_rt, r, 3)
            if c_val:
                num = c_val.split(".")[0] if "." in c_val else c_val
                current_section = Section(number=num, name=c_val)
                sheet.sections.append(current_section)
                current_u = None
                current_uu = None
                current_tt = None
                continue

        # tt within uu (subsection)
        if marker == "tt":
            f_val = cell_str(ws_rt, r, 6)
            if f_val and current_uu is not None:
                current_tt = TtSubsection(name=f_val)
                current_uu.subsections.append(current_tt)
            continue

        # Upper requirement (u)
        if marker == "u":
            c_val = cell_str(ws_rt, r, 3)
            if c_val == "要件":
                req_id = _escape_spec_newlines(cell_str(ws_rt, r, 4))
                text = get_formatted_text(ws_rt, r, 5, ws_data)
                spec_id = get_spec_id(ws_data, r, config)
                current_u = UpperReq(
                    req_id=req_id, text=text, spec_id=spec_id,
                    reason="", explanation=""
                )
                if current_section is not None:
                    current_section.upper_reqs.append(current_u)
                else:
                    sheet.upper_reqs.append(current_u)
                current_uu = None
                current_tt = None
            continue

        # Upper reason/explanation (o)
        if effective_marker == "o" and current_u is not None:
            label = cell_str(ws_rt, r, 4)
            content = get_formatted_text(ws_rt, r, 5, ws_data)
            if label == "理由":
                current_u.reason = content
            elif label == "説明":
                current_u.explanation = content
            continue

        # Lower requirement (uu)
        if marker == "uu":
            d_val = cell_str(ws_rt, r, 4)
            if d_val == "要件":
                req_id = _escape_spec_newlines(cell_str(ws_rt, r, 5))
                text = get_formatted_text(ws_rt, r, 6, ws_data)
                spec_id = get_spec_id(ws_data, r, config)
                current_uu = LowerReq(
                    req_id=req_id, text=text, spec_id=spec_id,
                    reason="", explanation=""
                )
                if current_u is not None:
                    current_u.lower_reqs.append(current_uu)
                current_tt = None
            continue

        # Lower reason/explanation (oo)
        if effective_marker == "oo" and current_uu is not None:
            label = cell_str(ws_rt, r, 5)
            content = get_formatted_text(ws_rt, r, 6, ws_data)
            if label == "理由":
                current_uu.reason = content
            elif label == "説明":
                current_uu.explanation = content
            continue

        # Specification row (ss) — all types go to specs
        if marker == "ss" and current_uu is not None:
            f_val = cell_str(ws_rt, r, 6)
            g_val = cell_str(ws_rt, r, 7)
            j_val = get_formatted_text(ws_rt, r, config["col_content"], ws_data)
            k_val = get_spec_id(ws_data, r, config)
            l_val = ""
            if config["col_usdm_ref"]:
                l_val = cell_str(ws_data, r, config["col_usdm_ref"])

            extras = {}
            for col_str, col_name, _ in extra_cols:
                col_letter = col_str.split("-")[0]
                col_num = openpyxl.utils.column_index_from_string(col_letter)
                val = cell_str(ws_rt, r, col_num)
                if val:
                    extras[col_name] = val

            spec = Specification(
                ss_type=f_val, number=g_val, content=j_val,
                spec_id=k_val, usdm_ref=l_val, extras=extras,
            )

            if current_tt is not None:
                current_tt.specs.append(spec)
            else:
                current_uu.specs.append(spec)
            continue

    return sheet


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

class BadSpecIdError(Exception):
    pass


def _escape_spec_newlines(val):
    """Replace actual newlines in spec_id with literal \\n for safe markdown output.

    Excel cells can contain newlines within spec IDs (e.g. multi-line auto-generated
    IDs).  These break markdown headings and file paths.  We escape them to the
    two-character sequence ``\\n`` so they survive the round-trip; md2usdm unescapes
    them back to real newlines when writing to Excel.
    """
    if not val:
        return val
    return val.replace('\n', '\\n')


def spec_id_inner(spec_id):
    """Extract inner part from 【PROJECT_ID_S01】 → PROJECT_ID_S01."""
    if not spec_id or spec_id == "-":
        return None
    m = re.match(r"【(.+)】", spec_id)
    return m.group(1) if m else None


def _spec_id_for_filename(spec_id):
    """Extract inner part of spec_id, sanitized for use as a filename.

    Literal ``\\n`` (from escaped newlines) is replaced with ``+`` to avoid
    invalid characters in file paths while keeping the ID readable.
    """
    name = spec_id_inner(spec_id)
    if name:
        name = name.replace('\\n', '+')
    return name


def u_dirname(u):
    name = _spec_id_for_filename(u.spec_id)
    if not name and not u.req_id:
        raise BadSpecIdError(f"No id found for {u}")
    return name if name else u.req_id


def u_index_filename(u):
    name = _spec_id_for_filename(u.spec_id)
    if not name and not u.req_id:
        raise BadSpecIdError(f"No id found for {u}")
    return f"{name}.md" if name else f"{u.req_id}.md"


def uu_filename(uu):
    name = _spec_id_for_filename(uu.spec_id)
    if not name and not uu.req_id:
        raise BadSpecIdError(f"No id found for {uu}")
    return f"{name}.md" if name else f"{uu.req_id}.md"


def build_uu_filename_map(u):
    """Build deduped filename map for all uu under a u. Returns {id(uu): filename}."""
    uu_map = {}
    used = {}
    for uu in u.lower_reqs:
        base = uu_filename(uu)
        if base not in used:
            used[base] = 1
            uu_map[id(uu)] = base
        else:
            used[base] += 1
            stem = base.rsplit(".", 1)[0]
            uu_map[id(uu)] = f"{stem}~#{used[base]}.md"
    return uu_map


def section_dirname(section):
    return f"sec{section.number.zfill(2)}"


def dedup_name(name, used_names):
    if name not in used_names:
        used_names.add(name)
        return name
    n = 2
    while f"{name}_{n}" in used_names:
        n += 1
    deduped = f"{name}_{n}"
    used_names.add(deduped)
    return deduped


# ---------------------------------------------------------------------------
# Markdown Generation Helpers
# ---------------------------------------------------------------------------

def md_escape_table(text):
    if not text:
        return ""
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    return text


def clean_req_text(text):
    if not text:
        return "(無題)"
    first_line = text.split("\n")[0].strip()
    first_line = first_line.replace("**", "").replace("~~", "")
    first_line = first_line.lstrip("■").strip()
    return first_line if first_line else "(無題)"


def make_nav_link(label, rel_path, title=""):
    if title:
        return f'↑ [{label}]({rel_path} "{title}")'
    return f"↑ [{label}]({rel_path})"


def make_link(label, rel_path, title=""):
    if title:
        return f'[{label}]({rel_path} "{title}")'
    return f"[{label}]({rel_path})"


def _collect_all_specs(uu):
    """Collect all specs from a uu (direct + subsection)."""
    all_specs = list(uu.specs)
    for tt in uu.subsections:
        all_specs.extend(tt.specs)
    return all_specs


def build_spec_table(specs, extra_col_names):
    """Build a Markdown spec table. Includes 種別 column only if multiple types."""
    if not specs:
        return ""

    # Determine if 種別 column is needed
    types = set(spec.ss_type for spec in specs)
    show_type = len(types) > 1

    # Determine which optional columns have data
    has_usdm = any(spec.usdm_ref and spec.usdm_ref != "-" for spec in specs)
    extra_with_data = []
    for name in extra_col_names:
        if any(spec.extras.get(name) and spec.extras[name] != "-" for spec in specs):
            extra_with_data.append(name)

    # Build headers
    headers = []
    if show_type:
        headers.append("種別")
    headers.extend(["#", "内容", "仕様番号"])
    if has_usdm:
        headers.append("USDM参照")
    headers.extend(extra_with_data)

    sep = [("---:" if h == "#" else "---") for h in headers]

    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(sep) + " |")

    for spec in specs:
        row = []
        if show_type:
            row.append(md_escape_table(spec.ss_type))
        row.extend([
            md_escape_table(spec.number),
            md_escape_table(spec.content),
            md_escape_table(spec.spec_id),
        ])
        if has_usdm:
            row.append(md_escape_table(spec.usdm_ref) if spec.usdm_ref and spec.usdm_ref != "-" else "")
        for name in extra_with_data:
            val = spec.extras.get(name, "")
            row.append(md_escape_table(val) if val and val != "-" else "")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Markdown File Generators
# ---------------------------------------------------------------------------

def generate_uu_file(uu, u, parent_rel_path, parent_label, parent_title, extra_col_names, filepath):
    title = clean_req_text(uu.text)
    lines = []
    lines.append(make_nav_link(parent_label, parent_rel_path, parent_title))
    lines.append("")
    lines.append(f"# {uu.spec_id}{title}")
    lines.append("")

    lines.append("## 要件")
    lines.append("")
    lines.append(uu.text if uu.text else "")
    lines.append("")

    lines.append("### 理由")
    lines.append("")
    lines.append(uu.reason if uu.reason else "記載無し")
    lines.append("")

    lines.append("### 説明")
    lines.append("")
    lines.append(uu.explanation if uu.explanation else "記載無し")
    lines.append("")

    if uu.specs or uu.subsections:
        lines.append("## 仕様")
        lines.append("")

    if uu.specs:
        lines.append(build_spec_table(uu.specs, extra_col_names))
        lines.append("")

    for tt in uu.subsections:
        lines.append(f"### {tt.name}")
        lines.append("")
        if tt.specs:
            lines.append(build_spec_table(tt.specs, extra_col_names))
            lines.append("")

    write_file(filepath, "\n".join(lines))


def generate_u_index(u, parent_rel_path, parent_label, parent_title, dirpath, uu_filename_map=None):
    title = clean_req_text(u.text)
    lines = []
    lines.append(make_nav_link(parent_label, parent_rel_path, parent_title))
    lines.append("")
    lines.append(f"# {u.spec_id}{title}")
    lines.append("")

    lines.append("## 要件")
    lines.append("")
    lines.append(u.text if u.text else "")
    lines.append("")

    lines.append("### 理由")
    lines.append("")
    lines.append(u.reason if u.reason else "記載無し")
    lines.append("")

    lines.append("### 説明")
    lines.append("")
    lines.append(u.explanation if u.explanation else "記載無し")
    lines.append("")

    if u.lower_reqs:
        lines.append("## 下位要件")
        lines.append("")
        for uu in u.lower_reqs:
            uu_title = clean_req_text(uu.text)
            fname = uu_filename_map[id(uu)] if uu_filename_map else uu_filename(uu)
            link = make_link(
                f"{uu.req_id} {uu_title}",
                f"./{fname}",
                uu.spec_id,
            )
            lines.append(f"- {link}")
        lines.append("")

    filepath = os.path.join(dirpath, u_index_filename(u))
    write_file(filepath, "\n".join(lines))


def generate_component_file(doc_id, comp_spec_id, comp_info, comp_reason, comp_explanation, outdir):
    """Generate the component u-file (e.g., PROJECT_ID.md) at the document root."""
    title = clean_req_text(comp_info) if comp_info else doc_id
    lines = []
    lines.append(f"# {comp_spec_id}{title}")
    lines.append("")

    lines.append("## 要件")
    lines.append("")
    lines.append(comp_info if comp_info else "")
    lines.append("")

    lines.append("### 理由")
    lines.append("")
    lines.append(comp_reason if comp_reason else "記載無し")
    lines.append("")

    lines.append("### 説明")
    lines.append("")
    lines.append(comp_explanation if comp_explanation else "記載無し")
    lines.append("")

    filepath = os.path.join(outdir, f"{doc_id}.md")
    write_file(filepath, "\n".join(lines))


def generate_sheet_index(sheet, outdir, sheet_dir, doc_info, u_dir_map):
    """Generate sheetNN/index.md with sections inline."""
    config = sheet.config
    doc_id = doc_info["doc_id"]
    comp_spec_id = doc_info["comp_spec_id"]
    excel_basename = doc_info["excel_basename"]
    base_comp_explanation = doc_info["comp_explanation"]
    base_comp_reason = doc_info["comp_reason"]

    comp_info = doc_info["comp_info"]
    comp_title = clean_req_text(comp_info) if comp_info else doc_id

    lines = []
    lines.append(make_nav_link(excel_basename, "../index.md"))
    lines.append("")
    lines.append(f"# {comp_spec_id}{sheet.sheet_name}")
    lines.append("")

    # Header section (extra columns only)
    extra_cols = config.get("header_extra_cols", [])
    if extra_cols:
        lines.append("## ヘッダー")
        lines.append("")
        col_widths_sheet = config.get("col_widths", {})
        extra_col_colors = config.get("extra_col_colors", ({}, {}))
        extra_bg, extra_fg = extra_col_colors
        extra_letters = []
        extra_w = []
        extra_r2 = []
        extra_r4 = []
        extra_bg_vals = []
        extra_fg_vals = []
        for col_str, text, merge_str in extra_cols:
            first_letter = col_str.split("-")[0]
            extra_letters.append(first_letter)
            w = col_widths_sheet.get(first_letter)
            extra_w.append(str(w) if w is not None else "")
            extra_r2.append(text)
            m = re.match(r'[A-Z]+(\d+):[A-Z]+(\d+)', merge_str)
            if m and int(m.group(2)) >= 4:
                extra_r4.append("↑")
            else:
                extra_r4.append("")
            extra_bg_vals.append(extra_bg.get(first_letter, ""))
            extra_fg_vals.append(extra_fg.get(first_letter, ""))

        # Compress color rows with ←
        def _compress_row(vals):
            result = list(vals)
            for i in range(len(result) - 1, 0, -1):
                if result[i] and result[i] == result[i - 1]:
                    result[i] = "←"
            return result

        lines.append("| 行 | " + " | ".join(extra_letters) + " |")
        lines.append("|---" + "|---" * len(extra_letters) + "|")
        if any(extra_w):
            lines.append("| 列 | " + " | ".join(extra_w) + " |")
        lines.append("| 2 | " + " | ".join(extra_r2) + " |")
        if any(extra_r4):
            lines.append("| 4 | " + " | ".join(extra_r4) + " |")
        if any(extra_bg_vals):
            lines.append("| 背景色 | " + " | ".join(_compress_row(extra_bg_vals)) + " |")
        if any(extra_fg_vals):
            lines.append("| 文字色 | " + " | ".join(_compress_row(extra_fg_vals)) + " |")
        lines.append("")

    # Section marker (only when non-default "tt")
    if config.get("section_marker") == "tt":
        lines.append("セクション区分: `tt`")
        lines.append("")

    # Requirement section — link to component file
    lines.append("## 要件")
    lines.append("")
    lines.append(f'[{doc_id}: {comp_title}](../{doc_id}.md "{comp_spec_id}")')
    lines.append("")

    # Reason/Explanation — only if overriding the base component values
    reason = sheet.component_reason or ""
    explanation = sheet.component_explanation or ""
    has_reason_override = reason and reason != base_comp_reason and reason not in ("記述無し", "記載無し")
    has_explanation_override = explanation and explanation != base_comp_explanation and explanation not in ("記述無し", "記載無し")

    if has_reason_override:
        lines.append("### 理由")
        lines.append("")
        lines.append(reason)
        lines.append("")

    if has_explanation_override:
        lines.append("### 説明")
        lines.append("")
        lines.append(explanation)
        lines.append("")

    if sheet.sections:
        for sec in sheet.sections:
            lines.append(f"## {sec.name}")
            lines.append("")
            for u in sec.upper_reqs:
                u_title = clean_req_text(u.text)
                sec_dir = section_dirname(sec)
                u_dir = u_dir_map[id(u)]
                u_idx = u_index_filename(u)
                link = make_link(
                    f"{u.req_id} {u_title}",
                    f"./{sec_dir}/{u_dir}/{u_idx}",
                    u.spec_id,
                )
                lines.append(f"- {link}")
            lines.append("")
    elif sheet.upper_reqs:
        lines.append("## 下位要件")
        lines.append("")
        for u in sheet.upper_reqs:
            u_title = clean_req_text(u.text)
            u_dir = u_dir_map[id(u)]
            u_idx = u_index_filename(u)
            link = make_link(
                f"{u.req_id} {u_title}",
                f"./{u_dir}/{u_idx}",
                u.spec_id,
            )
            lines.append(f"- {link}")
        lines.append("")

    write_file(os.path.join(outdir, sheet_dir, "index.md"), "\n".join(lines))


def generate_top_index(sheets, sheet_dirs, outdir, doc_info, header_layout, base_col_widths, base_colors=None):
    """Generate top-level index.md with header table and sheet list."""
    excel_basename = doc_info["excel_basename"]
    lines = []
    lines.append(f"# {excel_basename}")
    lines.append("")
    lines.append("## ヘッダー")
    lines.append("")

    # Parse header_layout to get per-column row2/row3 text + merge markers
    row2 = {}  # col_idx -> text
    row3 = {}  # col_idx -> text
    merge_end_r2 = {}  # col_idx -> "←{start}"
    merge_r3 = {}  # col_idx -> marker (↑, ↖, or ←)
    merge_r4 = {}  # col_idx -> marker
    max_header_col = 1
    for _, text, merge_str, _ in header_layout:
        m = re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', merge_str)
        if not m:
            continue
        min_col = column_index_from_string(m.group(1))
        min_row = int(m.group(2))
        max_col_mr = column_index_from_string(m.group(3))
        max_row = int(m.group(4))
        max_header_col = max(max_header_col, max_col_mr)
        start_letter = get_column_letter(min_col)
        cleaned = _clean_header_text(text)
        if min_row == 2:
            row2[min_col] = cleaned
            if min_col != max_col_mr:
                merge_end_r2[max_col_mr] = "←"
            # Row 3 markers omitted for row-2 merges; row 4 markers suffice
            if max_row >= 4:
                if min_col == max_col_mr:
                    merge_r4[min_col] = "↑"
                else:
                    merge_r4[min_col] = "↑"
                    merge_r4[max_col_mr] = "↖"
        elif min_row == 3:
            row3[min_col] = cleaned
            if min_col != max_col_mr:
                merge_r3[max_col_mr] = "←"
            if max_row >= 4:
                if min_col == max_col_mr:
                    merge_r4[min_col] = "↑"
                else:
                    merge_r4[min_col] = "↑"
                    merge_r4[max_col_mr] = "↖"

    # Column range: A to max(header, width)
    max_width_col = max((column_index_from_string(k) for k in base_col_widths), default=0)
    last_col = max(max_header_col, max_width_col)

    # Build per-column data
    bg_colors, fg_colors = base_colors if base_colors else ({}, {})
    col_letters = []
    r2_vals = []
    r3_vals = []
    r4_vals = []
    w_vals = []
    bg_vals = []
    fg_vals = []
    for c in range(1, last_col + 1):
        cl = get_column_letter(c)
        col_letters.append(cl)
        r2_vals.append(row2.get(c, merge_end_r2.get(c, "")))
        r3_vals.append(row3.get(c, merge_r3.get(c, "")))
        r4_vals.append(merge_r4.get(c, ""))
        w = base_col_widths.get(cl)
        w_vals.append(str(w) if w is not None else "")
        bg_vals.append(bg_colors.get(c, ""))
        fg_vals.append(fg_colors.get(c, ""))

    # Compress color rows: replace consecutive same values with ←
    def _compress_row(vals):
        result = list(vals)
        for i in range(len(result) - 1, 0, -1):
            if result[i] and result[i] == result[i - 1]:
                result[i] = "←"
        return result

    bg_compressed = _compress_row(bg_vals)
    fg_compressed = _compress_row(fg_vals)

    # Transposed table: columns=Excel columns, rows=width+header rows 2-4+colors
    lines.append("| 行 | " + " | ".join(col_letters) + " |")
    lines.append("|---" + "|---" * len(col_letters) + "|")
    lines.append("| 列 | " + " | ".join(w_vals) + " |")
    lines.append("| 2 | " + " | ".join(r2_vals) + " |")
    lines.append("| 3 | " + " | ".join(r3_vals) + " |")
    lines.append("| 4 | " + " | ".join(r4_vals) + " |")
    if any(bg_vals):
        lines.append("| 背景色 | " + " | ".join(bg_compressed) + " |")
    if any(fg_vals):
        lines.append("| 文字色 | " + " | ".join(fg_compressed) + " |")
    lines.append("")
    lines.append("## シート一覧")
    lines.append("")
    for sheet, sheet_dir in zip(sheets, sheet_dirs):
        lines.append(f"- [{sheet.sheet_name}](./{sheet_dir}/index.md)")
    lines.append("")
    write_file(os.path.join(outdir, "index.md"), "\n".join(lines))


def generate_all(sheets, sheet_dirs, outdir, doc_info, header_layout, base_colors=None):
    remove_md_files(outdir)

    base_col_widths = dict(sheets[0].config.get("col_widths", {}))
    generate_top_index(sheets, sheet_dirs, outdir, doc_info, header_layout, base_col_widths, base_colors)
    generate_component_file(
        doc_info["doc_id"], doc_info["comp_spec_id"],
        doc_info["comp_info"], doc_info["comp_reason"],
        doc_info["comp_explanation"], outdir,
    )

    for sheet, sheet_dir in zip(sheets, sheet_dirs):
        config = sheet.config
        full_sheet_dir = os.path.join(outdir, sheet_dir)
        extra_col_names = [text for _, text, _ in config.get("header_extra_cols", [])]

        # Build deduped u directory name map
        u_dir_map = {}
        used_dirs = set()

        all_u_lists = []
        if sheet.sections:
            for sec in sheet.sections:
                all_u_lists.append(sec.upper_reqs)
        if sheet.upper_reqs:
            all_u_lists.append(sheet.upper_reqs)

        for u_list in all_u_lists:
            for u in u_list:
                try:
                    base = u_dirname(u)
                    actual = dedup_name(base, used_dirs)
                except BadSpecIdError as err:
                    print(f"Ignoring u directory: {err}", file=sys.stderr)
                    actual = 'BAD_SPEC_ID' # suppress KeyError in later pass
                u_dir_map[id(u)] = actual

        try:
            generate_sheet_index(sheet, outdir, sheet_dir, doc_info, u_dir_map)
        except BadSpecIdError as err:
            print(f"Failed to generate sheet index: {err}")
            pass

        if sheet.sections:
            for sec in sheet.sections:
                sec_dir = os.path.join(full_sheet_dir, section_dirname(sec))

                for u in sec.upper_reqs:
                    actual_dir = u_dir_map[id(u)]
                    u_dir_path = os.path.join(sec_dir, actual_dir)
                    uu_fmap = build_uu_filename_map(u)
                    try:
                        generate_u_index(
                            u,
                            parent_rel_path="../../index.md",
                            parent_label=sheet.sheet_name,
                            parent_title="",
                            dirpath=u_dir_path,
                            uu_filename_map=uu_fmap,
                        )
                    except BadSpecIdError as err:
                        print(f"Failed to generate u index: {err}", file=sys.stderr)
                        pass

                    for uu in u.lower_reqs:
                        uu_path = os.path.join(u_dir_path, uu_fmap[id(uu)])
                        u_title = clean_req_text(u.text)
                        u_idx = u_index_filename(u)
                        generate_uu_file(
                            uu, u,
                            parent_rel_path=f"./{u_idx}",
                            parent_label=f"{u.spec_id}{u_title}",
                            parent_title=u.spec_id,
                            extra_col_names=extra_col_names,
                            filepath=uu_path,
                        )
        else:
            for u in sheet.upper_reqs:
                actual_dir = u_dir_map[id(u)]
                u_dir_path = os.path.join(full_sheet_dir, actual_dir)
                uu_fmap = build_uu_filename_map(u)
                try:
                    generate_u_index(
                        u,
                        parent_rel_path="../index.md",
                        parent_label=sheet.sheet_name,
                        parent_title="",
                        dirpath=u_dir_path,
                        uu_filename_map=uu_fmap,
                    )
                except BadSpecIdError as err:
                    print(f"Failed to generate u index: {err}", file=sys.stderr)
                    pass

                for uu in u.lower_reqs:
                    uu_path = os.path.join(u_dir_path, uu_fmap[id(uu)])
                    u_title = clean_req_text(u.text)
                    u_idx = u_index_filename(u)
                    generate_uu_file(
                        uu, u,
                        parent_rel_path=f"./{u_idx}",
                        parent_label=f"{u.spec_id}{u_title}",
                        parent_title=u.spec_id,
                        extra_col_names=extra_col_names,
                        filepath=uu_path,
                    )


def remove_md_files(base_dir):
    """Recursively delete all *.md files under base_dir"""
    maybe_emptied_dirs = []
    for root, dirs, files in os.walk(base_dir, topdown=True):
        # Don't recurse into dot directories such as .git
        dirs[:] = [n for n in dirs if not n.startswith(".")]
        files_to_delete = [n for n in files if n.endswith(".md")]
        for name in files_to_delete:
            os.remove(os.path.join(root, name))
        if files and len(files) == len(files_to_delete):
            maybe_emptied_dirs.append(root)

    for path in reversed(maybe_emptied_dirs):
        try:
            os.rmdir(path)
        except OSError as err:
            if err.errno != errno.ENOTEMPTY:
                raise


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def collect_all_specs(sheets):
    spec_ids = set()
    for sheet in sheets:
        all_u = list(sheet.upper_reqs)
        for sec in sheet.sections:
            all_u.extend(sec.upper_reqs)
        for u in all_u:
            for uu in u.lower_reqs:
                for spec in uu.specs:
                    if spec.spec_id and spec.spec_id != "-":
                        spec_ids.add(spec.spec_id)
                for tt in uu.subsections:
                    for spec in tt.specs:
                        if spec.spec_id and spec.spec_id != "-":
                            spec_ids.add(spec.spec_id)
    return spec_ids


def collect_excel_spec_ids(wb, sheet_configs):
    spec_ids = set()
    for sheet_name, config in sheet_configs.items():
        ws = wb[sheet_name]
        col = config["col_spec_id"]
        auto_col = config.get("col_auto")
        for r in range(config["data_start_row"], ws.max_row + 1):
            marker = cell_str(ws, r, 2)
            if marker == "ss":
                val = cell_str(ws, r, col)
                if val and val != "-":
                    spec_ids.add(_escape_spec_newlines(val))
                elif auto_col:
                    auto_val = cell_str(ws, r, auto_col)
                    if auto_val and not auto_val.startswith("＜"):
                        spec_ids.add(_escape_spec_newlines(f"【{auto_val}】"))
    return spec_ids


def verify_links(outdir):
    broken = []
    link_pattern = re.compile(r'\[.*?\]\(([^\s"]+)(?:\s+"[^"]*")?\)')

    for root, _dirs, files in os.walk(outdir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()

            for match in link_pattern.finditer(content):
                rel = match.group(1)
                target = os.path.normpath(os.path.join(root, rel))
                if not os.path.exists(target):
                    broken.append((fpath, rel))

    return broken


def count_generated_files(outdir):
    count = 0
    for _root, _dirs, files in os.walk(outdir):
        for f in files:
            if f.endswith(".md"):
                count += 1
    return count


def verify(sheets, sheet_configs, outdir, wb):
    print("\n" + "=" * 60)
    print("検証レポート")
    print("=" * 60)

    print("\n--- カウント検証 ---")
    for sheet in sheets:
        config = sheet.config
        all_u = list(sheet.upper_reqs)
        for sec in sheet.sections:
            all_u.extend(sec.upper_reqs)

        u_count = len(all_u)
        uu_count = sum(len(u.lower_reqs) for u in all_u)
        ss_count = tt_count = 0
        for u in all_u:
            for uu in u.lower_reqs:
                ss_count += len(uu.specs)
                tt_count += len(uu.subsections)
                for tt in uu.subsections:
                    ss_count += len(tt.specs)

        ws = wb[sheet.sheet_name]
        excel_u = excel_uu = excel_ss = excel_tt = 0
        for r in range(config["data_start_row"], ws.max_row + 1):
            m = cell_str(ws, r, 2)
            if m == "u":
                if cell_str(ws, r, 3) == "要件":
                    excel_u += 1
            elif m == "uu":
                excel_uu += 1
            elif m == "ss":
                excel_ss += 1
            elif m == "tt":
                if config["section_marker"] == "tt" and cell_str(ws, r, 3):
                    pass
                else:
                    excel_tt += 1

        u_ok = "OK" if u_count == excel_u else f"MISMATCH (excel={excel_u})"
        uu_ok = "OK" if uu_count == excel_uu else f"MISMATCH (excel={excel_uu})"
        ss_ok = "OK" if ss_count == excel_ss else f"MISMATCH (excel={excel_ss})"
        tt_ok = "OK" if tt_count == excel_tt else f"MISMATCH (excel={excel_tt})"

        print(f"\n  [{sheet.sheet_name}]")
        print(f"    u:  {u_count:4d}  {u_ok}")
        print(f"    uu: {uu_count:4d}  {uu_ok}")
        print(f"    ss: {ss_count:4d}  {ss_ok}")
        print(f"    tt: {tt_count:4d}  {tt_ok}")
        if sheet.sections:
            print(f"    sections: {len(sheet.sections)}")

    print("\n--- 仕様番号検証 ---")
    parsed_ids = collect_all_specs(sheets)
    excel_ids = collect_excel_spec_ids(wb, sheet_configs)
    missing = excel_ids - parsed_ids
    extra = parsed_ids - excel_ids
    print(f"  Excel: {len(excel_ids)} / パース済み: {len(parsed_ids)}")
    if missing:
        print(f"  !! 未変換: {len(missing)}")
        for sid in sorted(missing)[:10]:
            print(f"     {sid}")
    else:
        print("  全仕様番号を網羅: OK")
    if extra:
        print(f"  !! Excel にない番号: {len(extra)}")

    print("\n--- リンク検証 ---")
    broken = verify_links(outdir)
    if broken:
        print(f"  !! リンク切れ: {len(broken)}")
        for fpath, rel in broken[:10]:
            print(f"     {fpath} → {rel}")
    else:
        print("  全リンク正常: OK")

    print("\n--- ファイル数 ---")
    fcount = count_generated_files(outdir)
    print(f"  生成ファイル数: {fcount}")

    print("\n" + "=" * 60)
    print("検証完了")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 usdm2md.py <excel_path> [output_dir]")
        sys.exit(1)

    excel_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    print(f"Loading {excel_path} ...")
    wb_data = openpyxl.load_workbook(excel_path, data_only=True)
    wb_rt = openpyxl.load_workbook(excel_path, rich_text=True)

    excel_basename = os.path.splitext(os.path.basename(excel_path))[0]

    # Find USDM sheets
    usdm_sheet_names = [name for name in wb_data.sheetnames if is_usdm_sheet(wb_data[name])]
    print(f"  Found {len(usdm_sheet_names)} USDM sheets: {usdm_sheet_names}")

    # First pass: detect col_auto for each sheet to find base
    auto_cols = {}
    for name in usdm_sheet_names:
        auto_cols[name] = _detect_auto_col(wb_data[name]) or 18
    base_auto = min(auto_cols.values())

    # Second pass: detect full config for each sheet
    configs = {}
    for name in usdm_sheet_names:
        configs[name] = detect_sheet_config(wb_data[name], wb_rt[name], name, base_auto)

    # Read base header layout and colors (from a sheet with minimal col_auto)
    base_sheet_name = [n for n in usdm_sheet_names if auto_cols[n] == base_auto][0]
    header_layout = read_header_layout(wb_rt[base_sheet_name], base_auto)
    base_colors = read_header_colors(wb_rt[base_sheet_name], base_auto)

    # Read base component info (from first sheet, rows 5-7)
    first_ws_rt = wb_rt[usdm_sheet_names[0]]
    first_ws_data = wb_data[usdm_sheet_names[0]]
    comp_spec_id = _escape_spec_newlines(cell_str(first_ws_data, 5, 11))  # K5
    doc_id = spec_id_inner(comp_spec_id) or excel_basename.split("_")[0]
    comp_info = cell_str(first_ws_rt, 5, 4)  # D5
    comp_reason = get_formatted_text(first_ws_rt, 6, 4, first_ws_data)  # D6
    comp_explanation = get_formatted_text(first_ws_rt, 7, 4, first_ws_data)  # D7

    doc_info = {
        "excel_basename": excel_basename,
        "doc_id": doc_id,
        "comp_spec_id": comp_spec_id,
        "comp_info": comp_info,
        "comp_reason": comp_reason,
        "comp_explanation": comp_explanation,
    }

    # Parse all sheets
    sheets = []
    sheet_dirs = []
    for i, name in enumerate(usdm_sheet_names, 1):
        print(f"  Parsing: {name} ...")
        ws_rt = wb_rt[name]
        ws_data = wb_data[name]
        config = configs[name]
        sheet_data = parse_sheet(ws_rt, ws_data, name, config)
        sheets.append(sheet_data)
        sheet_dirs.append(f"sheet{i:02d}")

    # Generate
    print(f"\nGenerating Markdown to {output_dir}/ ...")
    generate_all(sheets, sheet_dirs, output_dir, doc_info, header_layout, base_colors)

    print("Running verification ...")
    verify(sheets, configs, output_dir, wb_data)


if __name__ == "__main__":
    main()
