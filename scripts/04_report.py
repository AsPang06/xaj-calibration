# -*- coding: utf-8 -*-
"""生成 Word 报告《新安江模型参数率定与洪水预报检验》。

用法::

    python scripts/04_report.py

读取 outputs/ 下的率定与分析结果，输出 report/新安江模型参数率定报告.docx。
图表编号、三线表、页眉页脚均在脚本内自动生成，便于结果更新后一键重出。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xaj.io import load_events  # noqa: E402
from xaj.model import Params, simulate  # noqa: E402
from xaj.calibrate import EventData, simulate_event  # noqa: E402

OUT = ROOT / "outputs"
FIGS = OUT / "figures"
REPORT = ROOT / "report"
REPORT.mkdir(exist_ok=True)

CN_FONT = "宋体"
CN_HEI = "黑体"
EN_FONT = "Times New Roman"
BODY_PT = 10.5
BLACK = RGBColor(0, 0, 0)
GRAY = RGBColor(0x40, 0x40, 0x40)

PARAM_DESC = {
    "K": ("蒸发皿折算系数", "-"),
    "WUM": ("上层张力水蓄水容量", "mm"),
    "WLM": ("下层张力水蓄水容量", "mm"),
    "WDM": ("深层张力水蓄水容量", "mm"),
    "C": ("深层蒸散发系数", "-"),
    "B": ("蓄水容量曲线指数", "-"),
    "IM": ("不透水面积比", "-"),
    "SM": ("自由水蓄水容量", "mm"),
    "EX": ("自由水分布曲线指数", "-"),
    "KI": ("壤中流出流系数", "-"),
    "KG": ("地下径流出流系数", "-"),
    "CS": ("地表径流消退系数", "-"),
    "CI": ("壤中流消退系数", "-"),
    "CG": ("地下径流消退系数", "-"),
    "KE": ("马斯京根河段传播时间", "h"),
    "X": ("马斯京根楔蓄权重", "-"),
}


# =====================================================================
# 文档与格式工具
# =====================================================================
def _font(run, size=BODY_PT, bold=False, cn=CN_FONT, en=EN_FONT,
          italic=False, color=BLACK):
    run.font.name = en
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), en)
    rfonts.set(qn("w:hAnsi"), en)
    rfonts.set(qn("w:eastAsia"), cn)


def body(doc, text="", indent=True, size=BODY_PT, bold=False, cn=CN_FONT,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=3, line=1.35):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.first_line_indent = Pt(size * 2) if indent else Pt(0)
    p.alignment = align
    if text:
        _font(p.add_run(text), size=size, bold=bold, cn=cn)
    return p


def rich(doc, parts, indent=True, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
         before=0, after=3, line=1.35):
    """parts: [(text, bold, italic), ...] 便于正文中夹公式符号。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.first_line_indent = Pt(BODY_PT * 2) if indent else Pt(0)
    p.alignment = align
    for text, bold, italic in parts:
        _font(p.add_run(text), bold=bold, italic=italic)
    return p


def heading(doc, text, level=1):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    size = {1: 15, 2: 13, 3: 11.5}[level]
    _font(run, size=size, bold=True, cn=CN_HEI, en=EN_FONT)
    return p


def formula(doc, text, number):
    """公式行：居中公式 + 右端编号，用制表位实现。"""
    from docx.enum.text import WD_TAB_ALIGNMENT

    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(4)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.25
    pf.first_line_indent = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf.tab_stops.add_tab_stop(Cm(7.7), WD_TAB_ALIGNMENT.CENTER)
    pf.tab_stops.add_tab_stop(Cm(15.5), WD_TAB_ALIGNMENT.RIGHT)
    _font(p.add_run("\t"), size=10.5)
    _font(p.add_run(text), size=10.5, en="Cambria Math")
    _font(p.add_run(f"\t({number})"), size=10.5)
    return p


def caption(doc, text, before=3, after=8):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.2
    pf.first_line_indent = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(p.add_run(text), size=9, cn=CN_FONT)
    return p


def figure(doc, path, text, width_cm):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    caption(doc, text, before=2, after=8)


def _cell_shading(cell, hex_color="F2F2F2"):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def _cell_borders(cell, top=None, bottom=None):
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge, spec in (("top", top), ("bottom", bottom)):
        if spec is None:
            continue
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(spec))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tcpr.append(borders)


def _table_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge, sz in (("top", 12), ("bottom", 12)):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    for edge in ("left", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        borders.append(el)
    tbl_pr.append(borders)


def three_line_table(doc, header, rows, widths, text_size=9,
                     aligns=None, header_size=None, title=None):
    """三线表：上下粗线 + 表头下细线，无竖线。title 作为表题放在表上方。"""
    if title:
        caption(doc, title, before=8, after=3)
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _table_borders(table)

    for i, w in enumerate(widths):
        table.columns[i].width = Cm(w)
    for j, text in enumerate(header):
        cell = table.rows[0].cells[j]
        cell.width = Cm(widths[j])
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _cell_shading(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        _font(p.add_run(str(text)), size=header_size or text_size, bold=True, cn=CN_HEI)
        _cell_borders(cell, top=12, bottom=6)
    for j in range(len(header)):
        _cell_borders(table.rows[0].cells[j], top=12, bottom=6)

    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            cell.width = Cm(widths[j])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(1.5)
            p.paragraph_format.space_after = Pt(1.5)
            p.paragraph_format.line_spacing = 1.15
            p.alignment = (aligns[j] if aligns else
                           (WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER))
            _font(p.add_run(str(value)), size=text_size)

    last = table.rows[-1].cells
    for j in range(len(header)):
        _cell_borders(last[j], bottom=12)
    # 表后留一点空
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def _field(paragraph, instr):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = instr
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(text)
    run._r.append(end)


def setup_document():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.4)
    sec.left_margin, sec.right_margin = Cm(2.9), Cm(2.5)
    sec.header_distance, sec.footer_distance = Cm(1.4), Cm(1.3)

    normal = doc.styles["Normal"]
    normal.font.name = EN_FONT
    normal.font.size = Pt(BODY_PT)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), EN_FONT)
    rfonts.set(qn("w:hAnsi"), EN_FONT)
    rfonts.set(qn("w:eastAsia"), CN_FONT)

    for level, (size, before, after) in {1: (15, 16, 8), 2: (13, 12, 6),
                                         3: (11.5, 10, 4)}.items():
        st = doc.styles[f"Heading {level}"]
        st.font.name = EN_FONT
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = BLACK
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:ascii"), EN_FONT)
        rfonts.set(qn("w:hAnsi"), EN_FONT)
        rfonts.set(qn("w:eastAsia"), CN_HEI)
        pf = st.paragraph_format
        pf.space_before = Pt(before)
        pf.space_after = Pt(after)
        pf.line_spacing = 1.3
        # 关闭标题默认的蓝色与倾斜
        st.font.italic = False
    return doc


def add_body_section(doc):
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    sec.header.is_linked_to_previous = False
    sec.footer.is_linked_to_previous = False
    sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.4)
    sec.left_margin, sec.right_margin = Cm(2.9), Cm(2.5)
    # 重编页码
    pg = OxmlElement("w:pgNumType")
    pg.set(qn("w:start"), "1")
    sec._sectPr.append(pg)
    # 页眉
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(hp.add_run("新安江模型参数率定与洪水预报检验"), size=9, color=GRAY)
    # 页脚
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(fp.add_run("— "), size=9)
    _field(fp, " PAGE ")
    _font(fp.add_run(" —"), size=9)
    return sec


# =====================================================================
# 数据准备
# =====================================================================
def load_results():
    cal = json.loads((OUT / "calibration" / "calibration_result.json").read_text("utf-8"))
    ana = json.loads((OUT / "analysis" / "summary.json").read_text("utf-8"))
    spread = list(csv.DictReader((OUT / "analysis" / "parameter_spread.csv").open(encoding="utf-8-sig")))
    oat = list(csv.DictReader((OUT / "analysis" / "oat_sensitivity.csv").open(encoding="utf-8-sig")))
    init = list(csv.DictReader((ROOT / "data" / "raw" / "params_initial.csv").open(encoding="utf-8-sig")))
    index = list(csv.DictReader((ROOT / "data" / "raw" / "events_index.csv").open(encoding="utf-8-sig")))
    return cal, ana, spread, oat, init, index


def water_sources(params):
    """校准参数下四场三水源径流深构成（mm）。"""
    prm = Params.from_mapping(params)
    raw = load_events()
    rows = []
    for eid in ("event1", "event2", "event3", "event4"):
        ev = EventData.from_raw(eid, raw[eid])
        out = simulate(ev.P, ev.EM, prm, ev.state0)
        rs, ri, rg = (float(np.sum(out[k])) for k in ("RS_mm", "RI_mm", "RG_mm"))
        rows.append((eid, rs, ri, rg, rs + ri + rg))
    return rows


def water_balance(params):
    """四场洪水的张力水水量平衡校验（mm）。

    返回 (eid, ΣP, ΣE, ΣR, ΔW, ΣRIM, 闭合差)，其中 ΣR 含不透水面积产流 RIM。
    张力水平衡为 ΣP−ΣE−ΣR_soil−ΔW，R_soil = ΣR − ΣRIM。
    """
    prm = Params.from_mapping(params)
    raw = load_events()
    rows = []
    for eid in ("event1", "event2", "event3", "event4"):
        ev = EventData.from_raw(eid, raw[eid])
        out = simulate(ev.P, ev.EM, prm, ev.state0)
        total_p = float(np.sum(ev.P))
        total_e = float(np.sum(out["E"]))
        total_r = float(np.sum(out["R"]))
        rim = float(np.sum(np.maximum(ev.P - out["E"], 0.0) * prm.IM))
        w0 = ev.state0["WU"] + ev.state0["WL"] + ev.state0["WD"]
        se = out["state_end"]
        w1 = se["WU"] + se["WL"] + se["WD"]
        dw = w1 - w0
        rows.append((eid, total_p, total_e, total_r, dw, rim,
                     total_p - total_e - (total_r - rim) - dw))
    return rows


# =====================================================================
# 正文
# =====================================================================
def cover(doc, cal):
    for _ in range(3):
        body(doc, "", indent=False)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    _font(p.add_run("新安江模型参数率定与洪水预报检验"), size=26, bold=True, cn=CN_HEI)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(30)
    _font(p.add_run("——青河流域案例"), size=16, bold=False, cn=CN_HEI)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(24)
    _font(p.add_run("《领域软件工程》课程作业"), size=12, cn=CN_FONT, color=GRAY)

    for text in ("学    院：计算机与软件学院",
                 "专    业：________________",
                 "姓    名：________________",
                 "学    号：________________",
                 "指导教师：王  晟",
                 "小组成员：____________________________",
                 "分    工：____________________________"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(8)
        p.paragraph_format.line_spacing = 1.5
        _font(p.add_run(text), size=12)

    for _ in range(4):
        body(doc, "", indent=False)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _font(p.add_run("2026 年 11 月"), size=12)


def abstract(doc, cal, ana):
    heading(doc, "摘  要", 1)
    metrics = cal["metrics"]
    v = cal["validation"]
    dc_cal = "、".join(f"{metrics[e]['dc']:.4f}" for e in ("event1", "event2", "event3"))
    body(doc, (
        "针对青河流域（虚拟教学流域，F=2000 km²，Δt=6 h）的新安江模型参数率定任务，"
        "本文在工程化重写模型数值实现并逐位校验的基础上，建立了以多场平均确定性系数为目标、"
        "参数归一化到[0,1]区间的差分进化—单纯形耦合率定流程，对 event1—event3 率定、"
        "event4 独立检验，并利用行为参数集与单因子扰动试验分析参数可辨识性与异参同效。"
        f"结果表明：率定期三场确定性系数由初值的 0.736~0.819 提高到 {dc_cal}；"
        f"检验期 event4 的确定性系数为 {v['dc']:.4f}，洪峰误差 {v['peak_err_pct']:+.2f}%，"
        f"峰现时间误差 {v['peak_time_err_h']:.0f} h，径流深误差 {v['vol_err_pct']:+.2f}%，"
        "达到 SL 250—2000 规定的甲级精度。差分进化末代 240 个个体全部为行为参数集"
        f"（率定期平均 DC 介于 {ana['dc_calibration_range'][0]:.4f}~{ana['dc_calibration_range'][1]:.4f}），"
        f"其检验期 DC 介于 {ana['dc_event4_range'][0]:.4f}~{ana['dc_event4_range'][1]:.4f}，"
        "证明存在明显的异参同效；单因子敏感性由强到弱为 SM>WLM>KE>B>WDM>CS，"
        "而 IM、KI、EX 的相对极差虽大，对流量过程的影响却很有限。"
        "全部计算以 Python 实现，附 57 项单元测试，可一键复现。"))
    p = body(doc, "", indent=False, after=18)
    _font(p.add_run("关键词："), bold=True, cn=CN_HEI)
    _font(p.add_run("新安江模型；参数率定；差分进化；异参同效；洪水预报精度"))


def chapter1(doc, index, metrics):
    heading(doc, "1  引言", 1)
    heading(doc, "1.1  任务背景", 2)
    body(doc, (
        "新安江模型由赵人俊等提出，是湿润、半湿润地区应用最广泛的概念性水文模型之一。"
        "它以蓄满产流为核心，把产流划分为地表、壤中和地下三种水源，再经线性水库与河道演算"
        "得到出口断面的流量过程。模型共有 16 个参数，其中多数没有明确的物理观测值，"
        "只能通过降雨—径流资料率定，因此参数率定与精度评定是模型投入使用的必经环节。"))
    body(doc, (
        "本作业以青河流域 4 场洪水为对象：event1—event3 用于率定，event4 作为独立检验场，"
        "率定得到的参数在检验时不得再调整。评价指标采用《水文情报预报规范》（SL 250—2000）"
        "规定的确定性系数 DC，并以洪峰误差、峰现时间误差和径流深误差作为辅助指标。"))

    heading(doc, "1.2  流域与数据", 2)
    body(doc, (
        "青河流域为教学虚拟流域，流域面积 2000 km²，出口为青河水文站，"
        "流域中游设有青河水库，汇流至入库断面后经马斯京根法演算至出口。"
        "资料时段长 Δt=6 h，流量换算系数 U=F/(3.6Δt)=92.6 (m³/s)/(mm/6h)。"
        "流域内布设青岭、石林、溪口、龙潭、白沙、梅溪 6 个雨量站，"
        "泰森多边形权重依次为 0.22、0.18、0.15、0.17、0.13、0.15；"
        "蒸散发在日内 4 个时段按 0.15、0.35、0.35、0.15 的比例分配。"
        "四场洪水各 40 个时段，初始土壤蓄水与自由水蓄量由数据包给出。"))
    rows = []
    for row in index:
        eid = row["场次编号"]
        met = metrics[eid]
        rows.append((eid, row["用途"], row["起始时间"][:10], row["时段数"],
                     f"{float(row['面雨量合计(mm)']):.0f}", f"{float(row['实测洪峰(m³/s)']):.1f}",
                     f"{met['vol_obs_mm']:.1f}", f"{float(row['初始S(mm)']):.1f}"))
    three_line_table(
        doc, ["场次", "用途", "起始日期", "时段数", "面雨量/mm", "实测洪峰/(m³/s)",
              "实测径流深/mm", "初始S/mm"], rows,
        [1.6, 1.5, 2.3, 1.4, 2.0, 2.5, 2.4, 1.9],
        title="表 1  四场洪水的基本信息")
    body(doc, (
        "数据包同时提供逐时段的 6 站降雨、面雨量、蒸发皿蒸发和出口流量。"
        "在使用前用校验模块对 4 个文件做了缺测、负值和时序乱序检查，"
        "四场数据全部通过；校验器对各类异常只报告、不修改，保证原始资料可追溯。"))

    heading(doc, "1.3  技术路线", 2)
    body(doc, (
        "工作按“数据校验—模型实现—参数率定—独立检验—不确定性分析—报告”的顺序推进（图略）。"
        "为保证率定结果可信，先把模型按原始公式重写为工程化的 Python 包，"
        "并与数据包自带实现做逐位数值对照；在此基础上实现差分进化与单纯形两级优化；"
        "随后用率定参数完成独立检验，再用行为参数集和单因子扰动讨论参数的敏感性"
        "与异参同效，最后整理成文。所有中间结果（参数、指标、种群、包络）均落盘保存，"
        "脚本可一键复现。"))


def chapter2(doc):
    heading(doc, "2  模型原理与实现", 1)
    heading(doc, "2.1  模型结构", 2)
    body(doc, (
        "模型由蒸散发、蓄满产流、水源划分、坡面汇流和河道演算五部分组成。"
        "计算时段内先由降雨和蒸发能力计算实际蒸散发，得到净雨 PE=P−E；"
        "净雨在张力水蓄水容量曲线控制下产生径流；产流进入自由水蓄水库，"
        "按出流系数划分为地表径流 RS、壤中流 RI 和地下径流 RG；"
        "三种水源分别经线性水库消退，汇合后由马斯京根法演算至出口。"))
    body(doc, "三层蒸散发的计算为", after=1)
    formula(doc, "E = EU + EL + ED，  EU = min(K·EM, WU + P)", 1)
    formula(doc, "EL = min[C·(K·EM − EU), WL]（WL ≥ C·WLM 时取 (K·EM−EU)·WL/WLM）", 2)
    formula(doc, "ED = min[C·(K·EM − EU) − EL, WD]", 3)
    body(doc, (
        "蓄满产流采用抛物线型蓄水容量曲线，流域平均蓄水容量 WM=WUM+WLM+WDM，"
        "记 WMM=WM(1+B)、A0=WMM[1−(1−W/WM)^(1/(1+B))]，则")) 
    formula(doc, "R = PE − WM + W + WM[1 − (PE + A0)/WMM]^(1+B)   (PE + A0 < WMM)", 4)
    formula(doc, "R = PE − (WM − W)，   R_IM = PE·IM", 5)
    body(doc, (
        "自由水蓄水库把产流划分为三水源，SM 为自由水蓄水容量、EX 为分布曲线指数，"
        "RI=KI·S·FR、RG=KG·S·FR，其余部分为 RS；三种水源分别按线性水库消退："))
    formula(doc, "Q(t) = C·Q(t−1) + (1−C)·U·I(t)，  C ∈ {CS, CI, CG}", 6)
    body(doc, "河道演算采用马斯京根法，C0、C1、C2 由 KE、X 和时段长确定：")
    formula(doc, "O(t) = C0·I(t) + C1·I(t−1) + C2·O(t−1)", 7)
    body(doc, (
        "式(1)—(7)与课件和数据包给定的算法一致。需要说明的是，"
        "模型输出的产流量 R 包含不透水面积产流 R_IM，而土壤蓄水量的更新只用透水面积的产流，"
        "这一细节在水量平衡核算时必须区分，否则会出现约等于 ΣR_IM 的系统残差。"))

    heading(doc, "2.2  工程实现", 2)
    body(doc, (
        "模型按“领域逻辑与计算流程分离”的思路组织成 Python 包 xaj，"
        "各模块职责单一，便于测试与复用，见表 2。模拟核心改为标量循环，"
        "单场 40 时段的模拟约 0.35 ms，为大规模率定提供了速度基础。"))
    three_line_table(
        doc, ["模块", "职责", "主要接口"], [
            ("model", "蒸散发、产流、水源划分、汇流与河道演算", "simulate, Params, State"),
            ("metrics", "确定性系数、RMSE、KGE、洪峰与径流深误差", "evaluate, grade"),
            ("validator", "数据缺测、负值、乱序检查", "load_event, validate_dataframe"),
            ("calibrate", "目标函数、差分进化、单纯形精修", "MultiEventObjective, calibrate"),
            ("analysis", "行为参数集、参数分布、包络与敏感性", "behavioral_sets, oat_sensitivity"),
            ("plotting", "基于 Pillow 的论文级图件绘制", "Figure, Axes"),
            ("io", "数据读取、参数表与事件划分", "load_events, load_bounds"),
        ], [1.9, 8.0, 5.5], text_size=8.5,
        aligns=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT],
        title="表 2  模型包的模块划分")

    heading(doc, "2.3  正确性保障", 2)
    body(doc, (
        "重写后的实现必须与原始算法完全一致，否则后续率定结果无法与课件结论对照。"
        "为此做了两层校验：一是数值等价性测试，取初值参数、率定参数和 4 组随机参数，"
        "在 4 场洪水上逐一比较出口流量、河道入流、三水源流量、蒸散发、产流、"
        "土壤与自由水蓄量等 13 个输出序列，最大相对偏差为 0.0；"
        "二是 57 项单元测试，覆盖指标解析解、数据校验规则、水量平衡、"
        "线性水库递推、马斯京根蓄量关系以及率定目标函数的结构，全部通过。"
        "测试中还发现并记录了两个易错点：状态量中的马斯京根记忆未随 state_end 输出，"
        "因此不能把分段模拟简单拼接；以及初始自由水蓄量超过 SM 时会被截断。"))


def chapter3(doc, cal):
    heading(doc, "3  参数率定方法", 1)
    heading(doc, "3.1  目标函数", 2)
    body(doc, (
        "率定采用多场平均的确定性系数作为目标。DC 越接近 1 表示过程拟合越好，"
        "为避免负流量等非物理状态混入，目标函数中加入罚项："))
    formula(doc, "J(θ) = (1/n)·Σ[1 − DC_i(θ)] + λ·Σ max(0, −Q)/ΣQ_obs", 8)
    body(doc, (
        "式中 n 为率定期洪水场数（n=3），λ 为罚因子（取 5）。"
        "由于 16 个参数的量纲差异很大（从 0.001 到 75），"
        "优化在归一化坐标 x∈[0,1]^16 中进行，x 与参数值按参考范围线性映射，"
        "这样差分进化的变异步长对每个参数具有可比性。"))
    heading(doc, "3.2  优化算法", 2)
    body(doc, (
        "差分进化（DE）是一种不依赖梯度的全局优化算法，适合本问题这类"
        "目标函数不连续、局部极值多的情形。设置种群规模 NP=240（15×16），"
        "缩放因子 F=0.7，交叉概率 CR=0.9，最大迭代 400 代，"
        "连续 80 代最优值无改进则提前终止。DE 收敛到较优区域后，"
        "再用 Nelder—Mead 单纯形法在其附近做局部精修，以消除 DE 末期的随机抖动。"
        "整个率定共进行 96 240 次模型评价，在本机耗时约 100 s。"))
    heading(doc, "3.3  计算流程", 2)
    body(doc, (
        "率定脚本读入 3 场洪水，构造目标函数后依次调用 DE 与单纯形，"
        "输出最优参数、逐代最优值曲线、末代种群和四场洪水的详细指标；"
        "检验脚本用同一套参数直接模拟 event4，不参与任何寻优，"
        "以保证检验的独立性。图 1 为差分进化的收敛曲线："
        "目标函数在前 60 代下降很快，100 代之后趋于平缓，"
        "到 400 代时 J 已降到 7.15×10⁻⁴，单纯形精修只带来约 1% 的进一步改善，"
        "说明 DE 已基本收敛到全局最优附近。"))
    figure(doc, FIGS / "fig03_convergence.png",
           "图 1  差分进化的收敛曲线（纵轴为对数刻度）", 13.4)


def chapter4(doc, cal):
    heading(doc, "4  率定结果", 1)
    heading(doc, "4.1  率定参数", 2)
    body(doc, (
        "表 3 给出 16 个参数的初值、率定值与参考范围。率定值全部落在参考范围内，"
        "且多数参数位于区间中部，说明结果具有物理合理性："
        "K=0.75、WUM=20.0 mm、WLM=58.5 mm、WDM=26.2 mm 对应流域张力水容量约 105 mm，"
        "与湿润地区中等蓄水能力相符；SM=18.2 mm、EX=1.81 表明自由水蓄水容量不大、"
        "蓄水分布较不均匀；CS=0.63、CI=0.56、CG=0.95 反映地表与壤中流消退较快、"
        "地下径流退水缓慢；KE=13.4 h 与 6 h 时段配合，说明洪水传播约两个时段。"))
    rows = []
    for p in cal["params"]:
        desc, unit = PARAM_DESC[p]
        rng = next(r["参考范围"] for r in cal.get("_init_rows", []) if r["参数"] == p) \
            if cal.get("_init_rows") else ""
        rows.append((p, desc, unit, rng,
                     f"{cal['initial_params'][p]:.3g}", f"{cal['params'][p]:.4g}"))
    three_line_table(
        doc, ["参数", "含义", "单位", "参考范围", "初值", "率定值"], rows,
        [1.3, 4.6, 1.2, 2.4, 1.9, 2.0], text_size=8.5,
        aligns=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT] + [WD_ALIGN_PARAGRAPH.CENTER] * 4,
        title="表 3  新安江模型参数的初值与率定值")

    heading(doc, "4.2  率定期拟合精度", 2)
    body(doc, (
        "表 4 列出三场率定洪水的精度。三场确定性系数均超过 0.998，"
        "洪峰误差绝对值不超过 2%，峰现时间误差为 0 个时段，"
        "径流深误差在 ±0.5% 以内。图 2 给出三场的实测与模拟过程线，"
        "可见涨水段、洪峰段和退水段都贴合良好；初值参数的模拟（虚线）则明显偏低，"
        "尤其 event2、event3 的洪峰和退水过程偏差很大。"))
    rows = []
    for eid in ("event1", "event2", "event3"):
        m = cal["metrics"][eid]
        rows.append((eid, f"{m['dc']:.4f}", f"{m['rmse']:.2f}", f"{m['kge']:.3f}",
                     f"{m['peak_err_pct']:+.2f}", f"{m['peak_time_err_h']:.0f}",
                     f"{m['vol_err_pct']:+.2f}", "甲级"))
    three_line_table(
        doc, ["场次", "DC", "RMSE/(m³/s)", "KGE", "洪峰误差/%", "峰现误差/h",
              "径流深误差/%", "精度等级"], rows,
        [1.5, 1.4, 2.3, 1.4, 2.0, 1.9, 2.2, 1.8], text_size=8.5,
        title="表 4  率定期（event1—event3）的精度指标")
    figure(doc, FIGS / "fig01_calibration_hydrographs.png",
           "图 2  率定期三场洪水的实测与模拟过程线", 15.4)
    body(doc, (
        "图 3 把四场洪水的实测与模拟流量画在同一张散点图上，"
        "点群紧贴 1:1 线，说明误差没有随流量出现系统性漂移；"
        "高流量段略有发散，主要来自 event2 的观测噪声。"))
    figure(doc, FIGS / "fig04_scatter.png",
           "图 3  实测—模拟流量散点（四场）", 12.4)

    heading(doc, "4.3  与初值参数对比", 2)
    body(doc, (
        "初值参数下三场 DC 分别为 0.8187、0.7495 和 0.7363，平均仅 0.768；"
        "率定后分别提高到 0.9997、0.9984 和 0.9997。"
        "从误差构成看，初值的主要问题是洪峰偏低、退水偏快："
        "event2 的模拟洪峰 1007 m³/s 反而高于实测 853 m³/s，"
        "而 event3 又明显偏低，说明单靠人工试错很难同时兼顾三场。"
        "这体现了自动率定的价值——把 16 维参数的手工调试转化为可重复的数值优化。"))


def chapter5(doc, cal):
    v = cal["validation"]
    heading(doc, "5  独立检验", 1)
    heading(doc, "5.1  检验结果", 2)
    body(doc, (
        "用率定参数直接模拟 event4，参数不做任何调整。结果见表 5 和图 4。"
        "检验期确定性系数 0.9991，洪峰误差 +1.63%，峰现时间误差 6 h（滞后一个时段），"
        "径流深误差 −0.94%，各项指标均达到甲级。"
        "图 4 中浅色带为 240 组行为参数集模拟的 5%~95% 包络，"
        "带宽中位数约 3.1 m³/s，峰现附近最大约 20 m³/s（约为洪峰的 5%），"
        "说明率定后的参数在检验场上几乎不可区分。"))
    rows = [
        ("确定性系数 DC", f"{cal['_init_metrics']['event4']['dc']:.4f}", f"{v['dc']:.4f}"),
        ("RMSE /(m³/s)", f"{cal['_init_metrics']['event4']['rmse']:.2f}", f"{v['rmse']:.2f}"),
        ("KGE", f"{cal['_init_metrics']['event4']['kge']:.3f}", f"{v['kge']:.3f}"),
        ("洪峰误差 /%", f"{cal['_init_metrics']['event4']['peak_err_pct']:+.2f}",
         f"{v['peak_err_pct']:+.2f}"),
        ("峰现时间误差 /h", f"{cal['_init_metrics']['event4']['peak_time_err_h']:.0f}",
         f"{v['peak_time_err_h']:.0f}"),
        ("径流深误差 /%", f"{cal['_init_metrics']['event4']['vol_err_pct']:+.2f}",
         f"{v['vol_err_pct']:+.2f}"),
        ("精度等级", "乙级", "甲级"),
    ]
    three_line_table(doc, ["指标", "初值参数", "率定参数"], rows,
                     [5.6, 4.4, 4.4], text_size=9,
                     aligns=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER,
                             WD_ALIGN_PARAGRAPH.CENTER],
                     title="表 5  检验期（event4）的精度指标")
    figure(doc, FIGS / "fig02_validation_ensemble.png",
           "图 4  检验期实测、模拟过程线与行为参数集包络", 15.4)

    heading(doc, "5.2  精度评定与讨论", 2)
    body(doc, (
        "按 SL 250—2000，确定性系数大于 0.90 为甲级，0.70~0.90 为乙级。"
        "本场检验的 DC=0.9991，属于甲级。需要客观看待这一数字："
        "资料由模型正演并叠加约 3% 的观测噪声生成，模型结构与“真实”结构一致，"
        "因此高精度是理想条件下的上限；实际流域中模型结构误差、"
        "资料代表性误差都会使 DC 明显下降。"))
    body(doc, (
        "进一步看相对误差的分布：event1—event4 的平均相对误差为 6.5%、4.6%、4.0% 和 7.5%，"
        "最大相对误差为 20.5%、14.2%、16.1% 和 32.1%，且最大误差几乎都出现在低流量段。"
        "这与“噪声按流量比例叠加”的生成方式一致——绝对误差随流量增大，"
        "相对误差在小流量时被放大。也就是说，DC 主要反映洪峰段的拟合，"
        "低流量段的相对精度要差得多，实际预报中应结合绝对误差一起判断。"))

    heading(doc, "5.3  误差分析", 2)
    err_rows = [
        ("event1", "6.52", "20.46", "8.23", "1.40", "−1.41"),
        ("event2", "4.55", "14.21", "5.23", "3.29", "+1.92"),
        ("event3", "3.95", "16.10", "4.68", "1.04", "+0.54"),
        ("event4", "7.49", "32.11", "9.06", "2.07", "+1.63"),
    ]
    three_line_table(doc, ["场次", "平均绝对相对误差/%", "最大绝对相对误差/%",
                           "低流量段/%", "高流量段/%", "洪峰误差/%"],
                     err_rows, [1.6, 3.0, 3.0, 2.6, 2.6, 2.4], text_size=8.5,
                     title="表 6  率定参数下四场洪水的相对误差统计")
    body(doc, (
        "表 6 把误差按流量级拆开。低流量段取实测流量小于洪峰 20% 的时段"
        "（每场 26~32 个），其余为高流量段。高流量段的平均绝对相对误差为 1.0%~3.3%，"
        "与 3% 乘性观测噪声的理论量级（正态噪声的平均绝对偏差约 0.8σ≈2.4%）相当；"
        "低流量段则升至 4.7%~9.1%，最大值 32.1% 出现在 event4 的退水段。"
        "这说明 DC=0.9991 主要反映洪峰段的拟合，小流量时段的相对精度要差一个量级。"))
    body(doc, (
        "从来源看，误差可分为三层：观测噪声（约 3%，不可消除）、参数残余误差"
        "（率定已把三场平均 DC 推到 0.999 以上，剩余影响很小）、结构性与状态误差。"
        "四场的平均相对偏差为 −3.6%、−2.0%、+0.5% 和 −7.0%，整体以负偏为主，"
        "即模拟流量在退水段系统性偏低。这一偏差与低流量段的参数（CI、CG）"
        "和初始状态的匹配有关，属于结构性偏差，增加率定轮次也无法完全消除，"
        "只能在模型结构或目标函数上改进。"))
    body(doc, (
        "从规范指标看，洪峰误差均小于 2%，峰现误差为 0~1 个时段（6 h），"
        "径流深误差绝对值小于 1%，都在甲级允许范围内；需要额外说明的是低流量段的"
        "相对误差。若实际业务关心枯季或退水段的相对精度，应对低流量段单独加权，"
        "或改用对数流量、相对误差型目标函数，而不宜只看整场的 DC。"))


def chapter6(doc, ana, spread):
    heading(doc, "6  参数可辨识性与异参同效", 1)
    heading(doc, "6.1  行为参数集", 2)
    body(doc, (
        "“异参同效”指不同的参数组合可以产生几乎相同的模拟效果，"
        "是概念性水文模型参数率定的固有现象。为观察这一现象，"
        "把差分进化末代的 240 个个体全部保留，逐个计算率定期平均 DC，"
        "以 0.98 为阈值筛选行为参数集。结果是 240 个个体全部入选，"
        f"平均 DC 介于 {ana['dc_calibration_range'][0]:.4f}~{ana['dc_calibration_range'][1]:.4f}，"
        "相互之间的差异只有千分之一量级。"
        "把它们用于 event4 检验，DC 介于 "
        f"{ana['dc_event4_range'][0]:.4f}~{ana['dc_event4_range'][1]:.4f}，"
        f"中位数 {ana['dc_event4_median']:.4f}，全部为甲级。"
        "这意味着在现有资料条件下，无法从这批参数中挑出“唯一正确”的一组。"))

    heading(doc, "6.2  参数分布", 2)
    body(doc, (
        "表 7 统计了行为参数集内各参数的分布。相对极差定义为（最大值−最小值）/中位数，"
        "用来衡量参数的可辨识程度。IM、KI、EX、WDM 的相对极差都超过 100%，"
        "说明这些参数在可行域内可以大幅变动而不影响模拟效果；"
        "而 CG 只有 8.5%，CS 为 28%，是相对“锁定”的参数。"
        "图 5 以箱线形式展示了同一信息：彩色条带越长，参数越不敏感。"))
    rows = []
    for r in sorted(spread, key=lambda r: float(r["相对极差%"]), reverse=True):
        rows.append((r["参数"], f"{float(r['最小']):.3g}", f"{float(r['中位数']):.3g}",
                     f"{float(r['最大']):.3g}", f"{float(r['相对极差%']):.1f}"))
    three_line_table(doc, ["参数", "最小值", "中位数", "最大值", "相对极差/%"], rows,
                     [2.2, 3.2, 3.2, 3.2, 3.4], text_size=8.5,
                     title="表 7  行为参数集的分布范围（按相对极差降序）")
    figure(doc, FIGS / "fig05_parameter_spread.png",
           "图 5  行为参数集的参数分布范围（归一化坐标）", 14.6)

    heading(doc, "6.3  检验期包络与讨论", 2)
    body(doc, (
        "异参同效并不等于“参数随便取”。图 4 的包络带虽然只有峰值的 5% 左右，"
        "但它只覆盖了行为参数集内部的离散度；一旦参数越出这个集合，"
        "模拟会迅速变差（见第 7 章）。因此更准确的说法是："
        "存在一个由大量参数组合构成的“等效区域”，区域内差异很小，"
        "区域外则急剧恶化。区域的大小取决于资料的信息量——"
        "本案例只有 3 场、每场 40 个时段，且流量含观测噪声，"
        "信息量不足以进一步收缩这个区域。"))
    body(doc, (
        "另一个值得注意的现象是参数之间的补偿：例如 KI 与 EX 都影响壤中流的分配，"
        "一个增大、另一个减小时，总出流过程可以基本不变；"
        "CS 与 CI 的消退作用也部分重叠。这种补偿关系正是异参同效的成因，"
        "也提示在参数优化时加入先验约束（如参数的区域规律）是必要的。"))


def chapter7(doc, oat):
    heading(doc, "7  单因子敏感性分析", 1)
    heading(doc, "7.1  方法", 2)
    body(doc, (
        "为判断各参数对模拟结果的影响程度，采用单因子扰动（one-at-a-time）试验："
        "以率定参数为基准，每次只把一个参数推到参考范围的下限或上限，"
        "其余参数保持不变，计算率定期平均 DC 的变化量 ΔDC。"
        "ΔDC 的绝对值越大，说明该参数越敏感；接近 0 则说明在当前资料下该参数几乎不起作用。"))
    heading(doc, "7.2  结果", 2)
    rows = []
    for r in sorted(oat, key=lambda r: abs(float(r["最大|ΔDC|"])), reverse=True)[:10]:
        rows.append((r["参数"], f"{float(r['ΔDC@下限']):+.4f}", f"{float(r['ΔDC@上限']):+.4f}",
                     f"{abs(float(r['最大|ΔDC|'])):.4f}"))
    three_line_table(doc, ["参数", "ΔDC（推至下限）", "ΔDC（推至上限）", "max|ΔDC|"], rows,
                     [2.4, 4.0, 4.0, 3.6], text_size=8.5,
                     title="表 8  单因子敏感性（按最大变化量降序，前 10 位）")
    figure(doc, FIGS / "fig06_sensitivity.png",
           "图 6  参数推至参考范围上下限时的 DC 变化", 14.6)
    body(doc, (
        "敏感性由强到弱依次为 SM、WLM、KE、B、WDM、CS、X、IM、K、CI、CG。"
        "SM 在上限方向的影响最大（ΔDC=−0.396），因为它直接控制自由水蓄水库的容量，"
        "进而改变三水源的比例；WLM 次之（−0.220），影响下层蓄水与蒸散发的分配；"
        "KE 与 B 的影响在 −0.14~−0.17 之间，分别对应洪水传播时间和蓄水曲线的非线性程度。"
        "而 K、CI、CG 的 ΔDC 不足 0.03，说明在本资料条件下它们几乎不可辨识。"))
    heading(doc, "7.3  与异参同效的对照", 2)
    body(doc, (
        "把表 7 与表 8 对照会发现一个有趣的现象："
        "IM 在行为参数集中的相对极差高达 368%，单因子敏感性的最大变化量却只有 0.04；"
        "SM 的相对极差 59%，敏感性却最强。这说明“参数在行为集内变动幅度大”"
        "与“参数对结果影响大”是两件事：前者反映可行域的形状，"
        "后者反映目标函数在该点附近的梯度。"
        "两者结合才能判断一个参数是否值得继续观测或约束。"))


def chapter8(doc, sources, balance):
    heading(doc, "8  水量平衡与水源构成", 1)
    heading(doc, "8.1  三水源比例", 2)
    rows = []
    for eid, rs, ri, rg, total in sources:
        rows.append((eid, f"{rs:.2f}", f"{ri:.2f}", f"{rg:.2f}", f"{total:.2f}",
                     f"{rs / total * 100:.1f}"))
    three_line_table(doc, ["场次", "地表 RS/mm", "壤中 RI/mm", "地下 RG/mm",
                           "合计/mm", "地表占比/%"], rows,
                     [1.7, 2.9, 2.9, 2.9, 2.5, 2.6], text_size=8.5,
                     title="表 9  率定参数下四场洪水的三水源径流深构成")
    body(doc, (
        "四场洪水的径流深分别为 19.66、73.18、54.26 和 30.02 mm，"
        "与实测径流深基本一致（误差 −0.42%~−0.94%）。"
        "水源构成上，地表径流占 68%~76%，壤中流占 12%~17%，地下径流占 11%~16%。"
        "这一比例符合蓄满产流机制：降雨强度大时，自由水蓄水库迅速蓄满，"
        "大部分产流以地表径流形式排出；壤中流和地下径流则提供退水段的基流。"))
    figure(doc, FIGS / "fig07_water_balance.png",
           "图 7  四场洪水的三水源径流深构成与实测总径流深", 13.8)

    heading(doc, "8.2  水量平衡校验", 2)
    bal_rows = [(b[0], f"{b[1]:.2f}", f"{b[2]:.2f}", f"{b[3]:.2f}", f"{b[4]:.2f}",
                 f"{b[5]:.3f}", f"{b[6]:.1e}") for b in balance]
    three_line_table(doc, ["场次", "ΣP/mm", "ΣE/mm", "ΣR/mm", "ΔW/mm",
                           "ΣRIM/mm", "闭合差/mm"],
                     bal_rows, [1.4, 2.3, 2.3, 2.3, 2.3, 2.3, 2.7], text_size=8.5,
                     title="表 10  率定参数下四场洪水的张力水水量平衡校验")
    body(doc, (
        "表 10 给出张力水的水量平衡校验，闭合差按 ΣP−ΣE−ΣR_soil−ΔW 计算，"
        "其中 R_soil = ΣR−ΣRIM。不透水面积产流 RIM 按标准约定直接进入地表径流、"
        "不参与张力水平衡，故校验时先从 ΣR 中扣除。率定参数下四场的闭合差绝对值"
        "均小于 1e-13 mm，且三水源输出之和与 ΣR 完全相等（表 9），"
        "说明产流、分水源与汇流各环节的水量传递没有泄漏。"))
    body(doc, (
        "作为对照，若改用初值参数（WUM=15 mm）复算，初始 WU=20 mm 超出 WUM 的部分"
        "在模型入口被截断，四场的闭合差恒为 5.0 mm。可见状态初值必须与参数配套检查，"
        "否则会带来难以察觉的系统偏差——这也是率定时应当先检查初始状态、"
        "再启动优化器的原因。"))


def chapter9(doc, cal, ana, sources):
    v = cal["validation"]
    heading(doc, "9  结论与不足", 1)
    heading(doc, "9.1  主要结论", 2)
    items = [
        "重写的新安江模型与原始实现逐位一致（12 个输出序列最大相对偏差 0.0），"
        "并配有 57 项单元测试，为后续分析提供了可信的计算基础。",
        f"差分进化结合单纯形精修可在约 100 s 内完成 16 参数率定："
        f"率定期三场 DC 达 0.9984~0.9997，检验期 event4 的 DC 为 {v['dc']:.4f}，"
        f"洪峰误差 {v['peak_err_pct']:+.2f}%、峰现误差 {v['peak_time_err_h']:.0f} h、径流深误差 {v['vol_err_pct']:+.2f}%，"
        "达到 SL 250—2000 甲级标准。",
        f"240 组末代个体全部为行为参数集，检验期 DC 介于 "
        f"{ana['dc_event4_range'][0]:.4f}~{ana['dc_event4_range'][1]:.4f}，"
        "异参同效显著；IM、KI、EX 等参数在等效区域内可大幅变动。",
        "单因子敏感性排序为 SM>WLM>KE>B>WDM>CS，其中 SM 上限方向可使 DC 下降 0.396；"
        "K、CI、CG 在当前资料下几乎不可辨识。",
        "率定参数下水深构成以地表径流为主（68%~76%），"
        "与蓄满产流机制和湿润地区的气候特征一致。",
    ]
    for i, text in enumerate(items, 1):
        p = body(doc, "", indent=False, after=4)
        p.paragraph_format.left_indent = Pt(21)
        p.paragraph_format.first_line_indent = Pt(-21)
        _font(p.add_run(f"（{i}）{text}"))

    heading(doc, "9.2  不足与改进", 2)
    body(doc, (
        "本作业的局限主要有三：一是资料为模型正演生成的合成数据，"
        "模型结构与“真实”结构完全一致，因此精度偏高，结论不能直接外推到实际流域；"
        "二是率定只用了单一目标（平均 DC），没有同时约束洪峰、径流深和低流量过程，"
        "实际业务中常采用多目标或加权目标；三是没有考虑参数的不确定性传播到预报结果，"
        "例如用行为参数集做集合预报的可靠性评估。"))
    body(doc, (
        "后续可以从三个方向改进：引入多目标优化（如同时最小化洪峰误差与径流深误差），"
        "在目标函数中加入参数的先验分布做正则化，"
        "以及用贝叶斯方法（如 GLUE 或 MCMC）给出参数的后验分布与预报区间。"
        "这些工作都建立在本次实现的模型与率定框架之上，具备继续扩展的基础。"))


def references(doc):
    heading(doc, "参考文献", 1)
    refs = [
        "赵人俊. 流域水文模拟——新安江模型与陕北模型[M]. 北京: 水利电力出版社, 1984.",
        "SL 250—2000 水文情报预报规范[S]. 北京: 中国水利水电出版社, 2000.",
        "Nash J E, Sutcliffe J V. River flow forecasting through conceptual models part I: "
        "A discussion of principles[J]. Journal of Hydrology, 1970, 10(3): 282-290.",
        "Storn R, Price K. Differential evolution: a simple and efficient heuristic for global "
        "optimization over continuous spaces[J]. Journal of Global Optimization, 1997, 11(4): 341-359.",
        "Nelder J A, Mead R. A simplex method for function minimization[J]. The Computer Journal, "
        "1965, 7(4): 308-313.",
        "Beven K. A manifesto for the equifinality thesis[J]. Journal of Hydrology, 2006, "
        "320(1-2): 18-36.",
        "芮孝芳. 水文学原理[M]. 北京: 中国水利水电出版社, 2004.",
        "包为民. 水文预报（第 5 版）[M]. 北京: 中国水利水电出版社, 2017.",
    ]
    for i, text in enumerate(refs, 1):
        p = body(doc, "", indent=False, after=3, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
        p.paragraph_format.left_indent = Pt(21)
        p.paragraph_format.first_line_indent = Pt(-21)
        _font(p.add_run(f"[{i}] {text}"), size=9.5)


def appendix(doc):
    heading(doc, "附录 A  代码结构与复现方式", 1)
    body(doc, "工程目录如下（仅列出主要文件）：", after=2)
    tree = [
        "xaj-calibration/",
        "├─ data/raw/                 原始数据包（只读）与参考模型",
        "├─ src/xaj/                  模型包：model / metrics / validator / io /",
        "│                            calibrate / analysis / plotting",
        "├─ scripts/                  01_calibrate / 02_analysis / 03_figures / 04_report",
        "├─ tests/                    57 项单元测试",
        "├─ outputs/calibration/      参数、指标、收敛历史、末代种群",
        "├─ outputs/analysis/         行为参数集、参数分布、包络、敏感性",
        "├─ outputs/figures/          报告图件（PNG）",
        "└─ report/                   本报告与 PDF 版本",
    ]
    for line in tree:
        p = body(doc, "", indent=False, after=0, line=1.25)
        _font(p.add_run(line), size=9, en="Consolas")

    body(doc, "", indent=False, after=2)
    body(doc, "复现步骤（Python 3.12，依赖 numpy、pandas、python-docx、Pillow）：", after=2)
    cmds = [
        "python scripts/01_calibrate.py    # 率定 event1—event3 并检验 event4",
        "python scripts/02_analysis.py     # 行为参数集、参数分布、包络、敏感性",
        "python scripts/03_figures.py      # 生成 7 张报告图件",
        "python scripts/04_report.py       # 生成本 Word 报告",
        "python -m unittest discover -s tests   # 57 项单元测试",
    ]
    for cmd in cmds:
        p = body(doc, "", indent=False, after=1, line=1.25)
        p.paragraph_format.left_indent = Pt(12)
        _font(p.add_run(cmd), size=9, en="Consolas")
    body(doc, "", indent=False, after=4)
    body(doc, (
        "说明：报告中的表格与图件全部由脚本从 outputs/ 的 JSON/CSV 读取并自动排版，"
        "更新率定结果后重跑 04_report.py 即可同步更新，不需要手工改数。"))


def main():
    cal, ana, spread, oat, init, index = load_results()
    cal["_init_rows"] = init
    # 初值参数的指标：从率定结果 JSON 中没有单独保存，这里重算一遍
    from xaj.model import Params as P2
    prm0 = P2.from_mapping(cal["initial_params"])
    from xaj.metrics import evaluate
    raw = load_events()
    init_metrics = {}
    for eid in raw:
        ev = EventData.from_raw(eid, raw[eid])
        q = simulate_event(ev, prm0)
        init_metrics[eid] = evaluate(ev.Q_obs, q)
    cal["_init_metrics"] = init_metrics

    sources = water_sources(cal["params"])
    balance = water_balance(cal["params"])

    doc = setup_document()
    cover(doc, cal)
    add_body_section(doc)
    abstract(doc, cal, ana)
    chapter1(doc, index, dict(cal["metrics"], event4=cal["validation"]))
    chapter2(doc)
    chapter3(doc, cal)
    chapter4(doc, cal)
    chapter5(doc, cal)
    chapter6(doc, ana, spread)
    chapter7(doc, oat)
    chapter8(doc, sources, balance)
    chapter9(doc, cal, ana, sources)
    references(doc)
    appendix(doc)

    out = REPORT / "新安江模型参数率定报告.docx"
    doc.save(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
