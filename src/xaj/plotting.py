# -*- coding: utf-8 -*-
"""轻量绘图库：基于 Pillow 的矢量风格图表（无 matplotlib 依赖）。

支持折线、散点、柱状、包络带、双轴（倒置雨量柱）、中文标签与图例。
内部以 ``SS`` 倍超采样绘制，最后用 LANCZOS 缩小，获得抗锯齿效果。
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
SS = 2  # 超采样倍数


def _font(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_PATH
    try:
        return ImageFont.truetype(path, max(6, int(round(size))))
    except OSError:
        return ImageFont.truetype(FONT_PATH, max(6, int(round(size))))


_HA = {"left": "l", "center": "m", "right": "r", "l": "l", "m": "m", "r": "r"}
_VA = {"top": "t", "bottom": "b", "center": "m", "middle": "m",
       "baseline": "s", "ascender": "a", "descender": "d",
       "t": "t", "b": "b", "m": "m", "s": "s", "a": "a", "d": "d"}


def _anchor(ha: str, va: str) -> str:
    return _HA.get(ha, "l") + _VA.get(va, "s")


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    """生成“好看”的刻度序列。"""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * mag
        if raw <= step:
            break
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 1e-9:
        if v >= lo - step * 1e-9:
            ticks.append(round(v, 10) + 0.0)   # +0.0 消除 -0.0
        v += step
    return ticks


def _dash_line(draw, pts: Sequence[tuple[float, float]], color, width: float,
               dash: Sequence[float], alpha: int = 255) -> None:
    """按 dash 模式逐段绘制折线。"""
    on, off = dash
    pattern_on = True
    remain = on
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg == 0:
            continue
        t = 0.0
        while t < seg:
            step = min(remain, seg - t)
            if pattern_on:
                xa, ya = x0 + (x1 - x0) * t / seg, y0 + (y1 - y0) * t / seg
                xb, yb = x0 + (x1 - x0) * (t + step) / seg, y0 + (y1 - y0) * (t + step) / seg
                draw.line([(xa, ya), (xb, yb)], fill=color + (alpha,), width=max(1, int(width)))
            t += step
            remain -= step
            if remain <= 1e-9:
                pattern_on = not pattern_on
                remain = on if pattern_on else off


def _rotated_text(layer: Image.Image, cx: float, cy: float, s: str,
                  font: ImageFont.FreeTypeFont, color, angle: float = 90) -> None:
    """把文字旋转后以 (cx, cy) 为中心贴到图层上（用于竖排的纵轴标题）。"""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(probe.textlength(s, font=font)) + 8
    th = int(font.size * 1.9) + 4
    tmp = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((tw / 2, th / 2), s, font=font, fill=color, anchor="mm")
    rot = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)
    layer.alpha_composite(rot, (int(cx - rot.width / 2), int(cy - rot.height / 2)))


class Axes:
    def __init__(self, fig: "Figure", rect: tuple[float, float, float, float],
                 xlim: tuple[float, float], ylim: tuple[float, float],
                 invert_y: bool = False):
        self.fig = fig
        self.xlim, self.ylim = xlim, ylim
        self.invert_y = invert_y
        W, H = fig.img.size
        x0, y0, x1, y1 = rect
        self.box = (x0 * W, (1 - y1) * H, x1 * W, (1 - y0) * H)
        self._x0, self._t, self._x1, self._b = self.box

    # -- 坐标变换 ---------------------------------------------------------
    def px(self, x: float) -> float:
        (x0, _, x1, _) = self.box
        xmin, xmax = self.xlim
        return x0 + (x - xmin) / (xmax - xmin) * (x1 - x0)

    def py(self, y: float) -> float:
        (_, t, _, b) = self.box
        ymin, ymax = self.ylim
        frac = (y - ymin) / (ymax - ymin)
        return b - frac * (b - t) if not self.invert_y else t + frac * (b - t)

    def _pts(self, xs, ys):
        return [(self.px(float(x)), self.py(float(y))) for x, y in zip(xs, ys)]

    # -- 绘制 -------------------------------------------------------------
    def plot(self, xs, ys, color="#1f4e79", width: float = 1.6,
             dash: Sequence[float] | None = None, alpha: int = 255) -> None:
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        pts = self._pts(xs, ys)
        w = width * self.fig.k
        if dash:
            _dash_line(d, pts, _rgb(color), w, [s * self.fig.k for s in dash], alpha)
        else:
            d.line(pts, fill=_rgb(color) + (alpha,), width=max(1, int(round(w))),
                   joint="curve")
        self.fig.composite(layer)

    def scatter(self, xs, ys, r: float = 3.0, color="#c00000",
                edge: str | None = "#ffffff", alpha: int = 255,
                marker: str = "o") -> None:
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        rr = r * self.fig.k
        fc = _rgb(color) + (alpha,)
        ec = (_rgb(edge) + (255,)) if edge else None
        w = max(1, int(rr * 0.3)) if edge else 0
        for x, y in zip(xs, ys):
            cx, cy = self.px(float(x)), self.py(float(y))
            if marker == "s":
                d.rectangle([cx - rr, cy - rr, cx + rr, cy + rr], fill=fc, outline=ec, width=w)
            elif marker == "^":
                d.polygon([(cx, cy - rr * 1.2), (cx - rr, cy + rr * 0.8),
                           (cx + rr, cy + rr * 0.8)], fill=fc, outline=ec)
            elif marker == "D":
                d.polygon([(cx, cy - rr * 1.25), (cx + rr, cy), (cx, cy + rr * 1.25),
                           (cx - rr, cy)], fill=fc, outline=ec)
            else:
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=fc, outline=ec, width=w)
        self.fig.composite(layer)

    def hbar(self, y_centers, values, height: float, color="#c00000",
             baseline: float = 0.0, alpha: int = 255) -> None:
        """水平条形图（用于敏感性龙卷风图）。"""
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        fc = _rgb(color) + (alpha,)
        for c, v in zip(y_centers, values):
            y0, y1 = self.py(c - height / 2), self.py(c + height / 2)
            x0, x1 = self.px(baseline), self.px(v)
            d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], fill=fc)
        self.fig.composite(layer)

    def bars(self, centers, heights, width: float, color="#8faadc",
             baseline: float = 0.0, alpha: int = 255) -> None:
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        for c, h in zip(centers, heights):
            x0, x1 = self.px(c - width / 2), self.px(c + width / 2)
            y0, y1 = self.py(baseline), self.py(baseline + h)
            d.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)],
                        fill=_rgb(color) + (alpha,))
        self.fig.composite(layer)

    def fill_between(self, xs, y_lo, y_hi, color="#9dc3e6", alpha: int = 90) -> None:
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        upper = self._pts(xs, y_hi)
        lower = self._pts(xs, y_lo)[::-1]
        d.polygon(upper + lower, fill=_rgb(color) + (alpha,))
        self.fig.composite(layer)

    def hline(self, y: float, color="#7f7f7f", width: float = 1.0,
              dash: Sequence[float] | None = None, alpha: int = 255) -> None:
        self.plot(self.xlim, [y, y], color, width, dash, alpha)

    def vline(self, x: float, color="#7f7f7f", width: float = 1.0,
              dash: Sequence[float] | None = None, alpha: int = 255) -> None:
        self.plot([x, x], self.ylim, color, width, dash, alpha)

    def text(self, x: float, y: float, s: str, size: float = 9,
             color: str = "#262626", ha: str = "left", va: str = "baseline",
             rotation: float = 0.0, bold: bool = False) -> None:
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        f = _font(size * self.fig.font_scale, bold)
        if rotation:
            _rotated_text(layer, self.px(x), self.py(y), s, f,
                          _rgb(color) + (255,), rotation)
        else:
            d.text((self.px(x), self.py(y)), s, font=f, fill=_rgb(color),
                   anchor=_anchor(ha, va))
        self.fig.composite(layer)

    # -- 坐标轴 -----------------------------------------------------------
    def frame(self, ticks_x: Sequence[float] | None = None,
              ticks_y: Sequence[float] | None = None,
              fmt_x: str = "{:g}", fmt_y: str = "{:g}",
              labels_x: Sequence[str] | None = None,
              labels_y: Sequence[str] | None = None,
              label_x: str = "", label_y: str = "",
              tick_size: float = 8, grid: bool = True,
              x_interval: int = 0) -> None:
        layer = self.fig.layer()
        d = ImageDraw.Draw(layer)
        k = self.fig.k
        col = _rgb("#404040") + (255,)
        (x0, t, x1, b) = self.box
        d.rectangle([x0, t, x1, b], outline=col, width=max(1, int(k)))
        # 网格
        if grid:
            for yt in ticks_y or []:
                yy = self.py(yt)
                _dash_line(d, [(x0, yy), (x1, yy)], _rgb("#d9d9d9"), k,
                           [3 * k, 3 * k])
        fs = tick_size * self.fig.font_scale
        f = _font(fs)
        for j, xt in enumerate(ticks_x or []):
            xx = self.px(xt)
            d.line([(xx, b), (xx, b + 4 * k)], fill=col, width=max(1, int(k)))
            lab = labels_x[j] if labels_x is not None else fmt_x.format(xt)
            d.text((xx, b + 6 * k), lab, font=f, fill=_rgb("#404040"), anchor="ma")
        for j, yt in enumerate(ticks_y or []):
            yy = self.py(yt)
            d.line([(x0 - 4 * k, yy), (x0, yy)], fill=col, width=max(1, int(k)))
            lab = labels_y[j] if labels_y is not None else fmt_y.format(yt)
            d.text((x0 - 6 * k, yy), lab, font=f,
                   fill=_rgb("#404040"), anchor="rm")
        if label_x:
            d.text(((x0 + x1) / 2, (b + 30 * k)), label_x, font=_font(fs),
                   fill=_rgb("#262626"), anchor="ma")
        if label_y:
            _rotated_text(layer, x0 - 42 * k, (t + b) / 2, label_y, f,
                          _rgb("#262626") + (255,), 90)
        self.fig.composite(layer)


class Figure:
    def __init__(self, width_in: float = 8.0, height_in: float = 5.0, dpi: int = 200):
        self.dpi = dpi
        self.px_size = (int(width_in * dpi), int(height_in * dpi))
        self.img = Image.new("RGB", (self.px_size[0] * SS, self.px_size[1] * SS), "white")
        self.k = SS * self.dpi / 72.0          # 1 pt → 像素
        self.font_scale = self.dpi * SS / 72.0

    def layer(self) -> Image.Image:
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def composite(self, layer: Image.Image) -> None:
        self.img = Image.alpha_composite(self.img.convert("RGBA"), layer).convert("RGB")

    def axes(self, rect: tuple[float, float, float, float],
             xlim: tuple[float, float], ylim: tuple[float, float],
             invert_y: bool = False) -> Axes:
        return Axes(self, rect, xlim, ylim, invert_y)

    def text(self, x: float, y: float, s: str, size: float = 9,
             color: str = "#262626", ha: str = "left", va: str = "baseline",
             bold: bool = False) -> None:
        layer = self.layer()
        d = ImageDraw.Draw(layer)
        W, H = self.img.size
        d.text((x * W, (1 - y) * H), s, font=_font(size * self.font_scale, bold),
               fill=_rgb(color), anchor=_anchor(ha, va))
        self.composite(layer)

    def legend(self, entries: Iterable[dict], x: float, y: float,
               size: float = 9, spacing: float = 1.9,
               horizontal: bool = False) -> None:
        """entries: [{label, color, dash, marker, fill}]，(x,y) 为图幅比例坐标。"""
        W, H = self.px_size
        layer = self.layer()
        d = ImageDraw.Draw(layer)
        f = _font(size * self.font_scale)
        span = size * spacing * self.font_scale
        if horizontal:
            cursor = x * W * SS
            yy = (1 - y) * H * SS
            for e in entries:
                cursor = self._draw_legend_item(d, e, cursor, yy, f)
        else:
            for i, e in enumerate(entries):
                yy = (1 - y) * H * SS + i * span
                self._draw_legend_item(d, e, x * W * SS, yy, f)
        self.composite(layer)

    def _draw_legend_item(self, d, e: dict, xx: float, yy: float, f) -> float:
        """在 (xx, yy) 处画一个图例项，返回下一个可用起点。"""
        if e.get("marker"):
            r = 4 * self.k
            shape = e.get("shape", "o")
            if shape == "s":
                d.rectangle([xx - r, yy - r, xx + r, yy + r], fill=_rgb(e["color"]))
            elif shape == "^":
                d.polygon([(xx, yy - r * 1.25), (xx - r, yy + r * 0.85),
                           (xx + r, yy + r * 0.85)], fill=_rgb(e["color"]))
            elif shape == "D":
                d.polygon([(xx, yy - r * 1.3), (xx + r, yy), (xx, yy + r * 1.3),
                           (xx - r, yy)], fill=_rgb(e["color"]))
            else:
                d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=_rgb(e["color"]))
            xx2 = xx + 16 * self.k
        elif e.get("fill"):
            d.rectangle([xx - 9 * self.k, yy - 6 * self.k, xx + 9 * self.k, yy + 6 * self.k],
                        fill=_rgb(e["color"]) + (int(e.get("alpha", 90)),))
            xx2 = xx + 16 * self.k
        else:
            pts = [(xx - 10 * self.k, yy), (xx + 10 * self.k, yy)]
            if e.get("dash"):
                _dash_line(d, pts, _rgb(e["color"]), 2 * self.k,
                           [s * self.k for s in e["dash"]])
            else:
                d.line(pts, fill=_rgb(e["color"]), width=max(1, int(2 * self.k)))
            xx2 = xx + 16 * self.k
        d.text((xx2, yy), e["label"], font=f, fill=_rgb("#262626"), anchor="lm")
        bbox = d.textbbox((xx2, yy), e["label"], font=f, anchor="lm")
        return bbox[2] + 14 * self.k

    def save(self, path: str, quality: int = 95) -> str:
        W, H = self.px_size
        img = self.img.resize((W, H), Image.LANCZOS)
        img.save(path, quality=quality, dpi=(self.dpi, self.dpi))
        return path


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


__all__ = ["Figure", "Axes", "nice_ticks", "FONT_PATH"]
