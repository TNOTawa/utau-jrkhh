import hashlib
import threading
import time
from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.patches as patches
import numpy as np
import soundfile as sf
from scipy.signal import spectrogram

from . import perf_trace

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

_PLOT_MAX_PTS = 4000
_SPEC_NFFT = 2048
_CACHE_DIR: Optional[Path] = None


def _cache_dir() -> Path:
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import tempfile
        _CACHE_DIR = Path(tempfile.gettempdir()) / "utau_waveform_cache"
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def _downsample(data: np.ndarray, max_pts: int = _PLOT_MAX_PTS) -> np.ndarray:
    if len(data) <= max_pts:
        return data
    step = len(data) // max_pts
    if step < 2:
        return data
    out = np.zeros(max_pts, dtype=np.float32)
    for i in range(max_pts):
        start = i * step
        end = min((i + 1) * step, len(data))
        chunk = data[start:end]
        out[i] = np.max(np.abs(chunk)) * (1 if chunk.mean() >= 0 else -1)
    return out


def _cache_key(wav_path: Path) -> str:
    mtime = wav_path.stat().st_mtime_ns if wav_path.exists() else 0
    raw = f"{wav_path.as_posix()}:{mtime}:v5"
    return hashlib.md5(raw.encode()).hexdigest()


def _load_or_compute(wav_path: Path) -> Optional[dict]:
    key = _cache_key(wav_path)
    wf_cache = _cache_dir() / (key + "_wf.npz")
    sp_cache = _cache_dir() / (key + "_sp.npz")

    t0 = perf_trace.trace("wf:check cache")
    if wf_cache.exists() and sp_cache.exists():
        try:
            wf = np.load(wf_cache)
            sp = np.load(sp_cache)
            perf_trace.end(t0, "wf:cache hit")
            return {
                "data": wf["data"], "sr": float(wf["sr"]),
                "dur": float(wf["dur"]),
                "sp_t": sp["t"], "sp_f": sp["f"], "sp_db": sp["db"],
            }
        except Exception:
            pass
    perf_trace.end(t0, "wf:cache miss")

    t1 = perf_trace.trace("wf:sf.read")
    try:
        raw, sr = sf.read(str(wav_path))
    except Exception:
        perf_trace.end(t1, "wf:sf.read FAIL")
        return None
    perf_trace.end(t1, "wf:sf.read done")
    if raw.ndim > 1:
        raw = raw[:, 0]
    dur = len(raw) / sr

    t2 = perf_trace.trace("wf:downsample")
    ds = _downsample(raw)
    perf_trace.end(t2, "wf:downsample")

    t3 = perf_trace.trace("wf:spectrogram")
    freqs, times, sxx = spectrogram(
        raw, fs=sr, nperseg=_SPEC_NFFT,
        noverlap=_SPEC_NFFT // 2, mode="magnitude")
    sxx_db = 20 * np.log10(sxx + 1e-12)
    db_min, db_max = np.percentile(sxx_db, [1, 99])
    sxx_db = np.clip(sxx_db, db_min, db_max).astype(np.float32)
    perf_trace.end(t3, "wf:spectrogram")

    del raw

    t4 = perf_trace.trace("wf:save cache")
    try:
        np.savez(wf_cache, data=ds, sr=sr, dur=dur)
        np.savez(sp_cache, t=times, f=freqs, db=sxx_db)
    except Exception:
        pass
    perf_trace.end(t4, "wf:save cache")

    return {
        "data": ds, "sr": float(sr), "dur": dur,
        "sp_t": times, "sp_f": freqs, "sp_db": sxx_db,
    }


class WaveformDisplay:
    def __init__(self, parent, width: int = 500, height: int = 200):
        self.parent = parent
        self.figure = Figure(figsize=(width / 100, height / 100), dpi=100)
        self.figure.set_facecolor("#2b2b2b")
        self.ax_wave = self.figure.add_subplot(211)
        self.ax_spec = self.figure.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)

        self._total_duration: float = 0.0
        self._spec_times: Optional[np.ndarray] = None
        self._spec_freqs: Optional[np.ndarray] = None
        self._spec_db_full: Optional[np.ndarray] = None
        self._spec_img: Optional[object] = None
        self._pan_start: Optional[tuple] = None
        self._pan_xlim_start: Optional[tuple] = None
        self._pending: Optional[dict] = None
        self._redraw_id: Optional[str] = None
        self._motion_count = 0

        self._last_result: Optional[dict] = None
        self._last_params: Optional[dict] = None
        self._mouse_in: bool = False
        self._last_xdata: Optional[float] = None

        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("figure_enter_event", self._on_figure_enter)
        self.canvas.mpl_connect("figure_leave_event", self._on_figure_leave)

        self._setup_style()
        self.canvas.draw()

    def _schedule_redraw(self):
        if self._redraw_id is not None:
            self.parent.after_cancel(self._redraw_id)
        self._redraw_id = self.parent.after(16, self._do_redraw)

    def _do_redraw(self):
        self._redraw_id = None
        self.canvas.draw_idle()

    def _setup_style(self):
        for ax in (self.ax_wave, self.ax_spec):
            ax.set_facecolor("#1e1e1e")
            ax.tick_params(colors="#666666", labelsize=7)
            ax.spines["bottom"].set_color("#444444")
            ax.spines["left"].set_visible(False)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.yaxis.set_visible(False)
        self.ax_wave.tick_params(bottom=False, labelbottom=False)
        self.figure.subplots_adjust(
            left=0.02, right=0.99, top=0.97, bottom=0.04,
            hspace=0.05)

    def load_with_oto(self, wav_path: Path, offset_ms: float, consonant_ms: float,
                      cutoff_ms: float, overlap_ms: float = 0.0,
                      preutterance_ms: float = 0.0):
        perf_trace.trace("wf:load_with_oto")
        self._pending = {
            "wav_path": wav_path,
            "offset_ms": offset_ms,
            "consonant_ms": consonant_ms,
            "cutoff_ms": cutoff_ms,
            "overlap_ms": overlap_ms,
            "preutterance_ms": preutterance_ms,
        }
        threading.Thread(target=self._load_async, daemon=True).start()

    def _load_async(self):
        if not self._pending:
            return
        t0 = perf_trace.trace("wf:_load_async")
        p = self._pending
        self._pending = None
        result = _load_or_compute(p["wav_path"])
        perf_trace.end(t0, "wf:_load_async total")
        if result is None:
            self.parent.after(0, self._render_error)
            return
        self.parent.after(
            0, lambda: self._render(
                result,
                p["offset_ms"], p["consonant_ms"], p["cutoff_ms"],
                p["overlap_ms"], p["preutterance_ms"]))

    def _render_error(self):
        for ax in (self.ax_wave, self.ax_spec):
            ax.clear()
        self._setup_style()
        self._total_duration = 0
        self._spec_times = None
        self._spec_freqs = None
        self._spec_db_full = None
        self._spec_img = None
        self._pan_start = None
        self._pan_last_xdata = None
        self._last_result = None
        self._last_params = None
        self.canvas.draw_idle()

    def _draw_oto_markers(self, offset_s: float, consonant_end_s: float,
                          segment_end_s: float, overlap_s: float,
                          preutterance_s: float, dur: float, amp_val: float):
        if not (0 <= offset_s <= dur):
            return
        markers = [
            (offset_s, "#339af0", "--", 0.9, None),
            (overlap_s, "#a3e635", "-.", 1.0, "OVL"),
            (preutterance_s, "#ff3366", "-", 1.3, "PRE"),
            (consonant_end_s, "#da77f2", ":", 0.9, None),
            (segment_end_s, "#ff922b", "--", 0.9, None),
        ]
        for x, color, ls, lw, label in markers:
            if not (0 <= x <= dur):
                continue
            for ax in (self.ax_wave, self.ax_spec):
                ax.axvline(x=x, color=color, linestyle=ls, linewidth=lw,
                           alpha=0.9, zorder=4)
            if label:
                self.ax_wave.text(x, amp_val * 0.88, label, color=color,
                                  fontsize=8, ha='center', va='top',
                                  fontweight='bold', zorder=5)

    @staticmethod
    def _downsample_2d(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
        """将 2D 数组降采样到目标尺寸，使用 max 聚合保留峰值。"""
        h, w = arr.shape
        if h <= target_h and w <= target_w:
            return arr

        result = arr
        if h > target_h:
            step_h = h // target_h
            trim_h = step_h * target_h
            result = result[:trim_h].reshape(target_h, step_h, w).max(axis=1)
            h = target_h

        if w > target_w:
            step_w = w // target_w
            trim_w = step_w * target_w
            result = result[:, :trim_w].reshape(h, target_w, step_w).max(axis=2)

        return result

    def _update_spec_view(self):
        """根据当前 xlim 动态裁剪并降采样频谱数据，减少 draw_idle 工作量。"""
        if self._spec_img is None or self._spec_db_full is None:
            return

        xlim = self.ax_spec.get_xlim()
        x0, x1 = max(0.0, xlim[0]), min(self._total_duration, xlim[1])
        if x0 >= x1:
            return

        fig_w, fig_h = self.canvas.get_width_height()
        pos = self.ax_spec.get_position()
        target_w = max(100, int(fig_w * pos.width * 1.5))
        target_h = max(50, int(fig_h * pos.height * 1.5))

        t = self._spec_times
        f = self._spec_freqs

        t_idx_start = max(0, np.searchsorted(t, x0, side='left') - 1)
        t_idx_end = min(len(t), np.searchsorted(t, x1, side='right') + 1)
        if t_idx_start >= t_idx_end:
            return

        db_crop = self._spec_db_full[:, t_idx_start:t_idx_end]
        db_ds = self._downsample_2d(db_crop, target_h, target_w)

        t_start = t[t_idx_start]
        t_end = t[min(t_idx_end - 1, len(t) - 1)]

        self._spec_img.set_data(db_ds)
        self._spec_img.set_extent([t_start, t_end, f[0], f[-1]])
        # 初始数据为全零导致 vmin=vmax=0，set_data 后需恢复颜色范围
        self._spec_img.autoscale()

    def _render(self, result: dict, offset_ms: float, consonant_ms: float,
                cutoff_ms: float, overlap_ms: float, preutterance_ms: float,
                preserve_view: bool = False):
        t0 = perf_trace.trace("wf:_render")
        self._last_result = result
        self._last_params = {
            "offset_ms": offset_ms, "consonant_ms": consonant_ms,
            "cutoff_ms": cutoff_ms, "overlap_ms": overlap_ms,
            "preutterance_ms": preutterance_ms,
        }
        data = result["data"]
        dur = result["dur"]

        old_xlim = self.ax_wave.get_xlim() if self._total_duration > 0 else None

        self.ax_wave.clear()
        self.ax_spec.clear()
        self._setup_style()

        self._total_duration = dur
        time_axis = np.linspace(0, dur, len(data))

        offset_s = offset_ms / 1000.0
        consonant_end_s = offset_s + consonant_ms / 1000.0
        segment_end_s = offset_s + abs(cutoff_ms) / 1000.0
        overlap_s = offset_s + overlap_ms / 1000.0
        preutterance_s = offset_s + preutterance_ms / 1000.0

        amp_val = max(abs(data.min()), abs(data.max())) * 1.1 or 1.0

        # 1. 淡色完整波形（外部区域）
        self.ax_wave.plot(time_axis, data, color="#4ec9b0", linewidth=0.35,
                          alpha=0.35, zorder=1)

        # 2. 音素有效区域高亮背景（完整矩形填充）
        if 0 <= offset_s < segment_end_s:
            rect = patches.Rectangle(
                (offset_s, -amp_val), segment_end_s - offset_s, 2 * amp_val,
                linewidth=0, facecolor='#0a0a12',
                alpha=0.98, zorder=2)
            self.ax_wave.add_patch(rect)

            # 3. 区域内亮色波形（裁剪到高亮区域）
            clip_rect = patches.Rectangle(
                (offset_s, -amp_val), segment_end_s - offset_s, 2 * amp_val,
                transform=self.ax_wave.transData)
            self.ax_wave.plot(time_axis, data, color="#4ec9b0", linewidth=0.8,
                              alpha=1.0, clip_path=clip_rect, zorder=3)

            # 4. “厂”字形折线边框：offset底部 → OVL顶部 → segment_end顶部
            self.ax_wave.plot(
                [offset_s, overlap_s, segment_end_s],
                [-amp_val, amp_val, amp_val],
                color='#5b8cff', linewidth=1.8,
                solid_joinstyle='miter', alpha=0.98, zorder=4)

        self._draw_oto_markers(offset_s, consonant_end_s, segment_end_s,
                               overlap_s, preutterance_s, dur, amp_val)

        if preserve_view and old_xlim is not None:
            lo, hi = old_xlim
            lo = max(0.0, lo)
            hi = min(dur, hi)
            if hi - lo < 0.001:
                lo, hi = 0, dur
            self.ax_wave.set_xlim(lo, hi)
        else:
            self.ax_wave.set_xlim(0, dur)
        self.ax_wave.set_ylim(-amp_val, amp_val)

        self._spec_times = result.get("sp_t")
        self._spec_freqs = result.get("sp_f")
        self._spec_db_full = result.get("sp_db")
        self._spec_img = None

        if self._spec_times is not None:
            self._spec_img = self.ax_spec.imshow(
                np.zeros((2, 2), dtype=np.float32),
                aspect="auto", origin="lower",
                extent=[0, dur, self._spec_freqs[0], self._spec_freqs[-1]],
                cmap="inferno", interpolation="bilinear",
                rasterized=True)
            if preserve_view and old_xlim is not None:
                lo, hi = old_xlim
                lo = max(0.0, lo)
                hi = min(dur, hi)
                if hi - lo < 0.001:
                    lo, hi = 0, dur
                self.ax_spec.set_xlim(lo, hi)
            else:
                self.ax_spec.set_xlim(0, dur)
            self._update_spec_view()
        else:
            self._spec_times = None
            self._spec_freqs = None
            self._spec_db_full = None

        self.canvas.draw_idle()
        perf_trace.end(t0, "wf:_render")

    def clear(self):
        for ax in (self.ax_wave, self.ax_spec):
            ax.clear()
        self._setup_style()
        self._total_duration = 0
        self._spec_times = None
        self._spec_freqs = None
        self._spec_db_full = None
        self._spec_img = None
        self._last_result = None
        self._last_params = None
        self.canvas.draw_idle()

    def get_widget(self):
        return self.canvas.get_tk_widget()

    def _set_xlim(self, lo: float, hi: float):
        self.ax_wave.set_xlim(lo, hi)
        if self._spec_times is not None:
            self.ax_spec.set_xlim(lo, hi)
        self._update_spec_view()

    def _zoom(self, scale: float, center: Optional[float] = None):
        if self._total_duration <= 0:
            return
        xlim = self.ax_wave.get_xlim()
        if center is None:
            center = (xlim[0] + xlim[1]) / 2
        new_range = (xlim[1] - xlim[0]) * scale
        new_range = max(0.01, min(new_range, self._total_duration))
        half = new_range / 2
        new_min = center - half
        new_max = center + half
        if new_min < 0:
            new_min, new_max = 0, new_range
        if new_max > self._total_duration:
            new_max = self._total_duration
            new_min = max(0, new_max - new_range)
        self._set_xlim(new_min, new_max)
        self._schedule_redraw()

    def zoom_in(self):
        self._zoom(0.75)

    def zoom_out(self):
        self._zoom(1.35)

    def _on_scroll(self, event):
        if self._total_duration <= 0:
            return
        xlim = self.ax_wave.get_xlim()
        center = event.xdata if event.xdata else (xlim[0] + xlim[1]) / 2
        scale = 0.75 if event.button == "up" else 1.35
        self._zoom(scale, center)

    def _on_press(self, event):
        if event.button == 1 and event.key is None and event.xdata:
            self._pan_start = (event.x, event.xdata)
            self._pan_last_xdata = event.xdata
            # 拖动期间隐藏频谱图 axes，将 draw 耗时从 ~30ms 降到 ~10ms，保证流畅
            self.ax_spec.set_visible(False)

    def _on_release(self, event):
        self._pan_start = None
        self._pan_last_xdata = None
        # 恢复频谱图可见性并更新细节
        self.ax_spec.set_visible(True)
        self._update_spec_view()
        self.canvas.draw_idle()
        perf_trace.end(
            perf_trace.trace(""),
            f"wf:pan frames={self._motion_count}")
        self._motion_count = 0

    def _pan(self, dx_data: float):
        if self._total_duration <= 0:
            return
        xlim = self.ax_wave.get_xlim()
        new_lo = xlim[0] + dx_data
        new_hi = xlim[1] + dx_data
        if new_lo < 0:
            new_hi -= new_lo
            new_lo = 0
        if new_hi > self._total_duration:
            new_lo -= (new_hi - self._total_duration)
            new_hi = self._total_duration
        if new_lo < 0:
            new_lo = 0
        self._set_xlim(new_lo, new_hi)
        self._schedule_redraw()

    def pan_left(self):
        xlim = self.ax_wave.get_xlim()
        span = xlim[1] - xlim[0]
        self._pan(-span * 0.15)

    def pan_right(self):
        xlim = self.ax_wave.get_xlim()
        span = xlim[1] - xlim[0]
        self._pan(span * 0.15)

    def _on_figure_enter(self, event):
        self._mouse_in = True

    def _on_figure_leave(self, event):
        self._mouse_in = False

    def get_mouse_time(self) -> Optional[float]:
        return self._last_xdata if self._mouse_in else None

    def update_params(self, offset_ms: float, consonant_ms: float,
                      cutoff_ms: float, overlap_ms: float = 0.0,
                      preutterance_ms: float = 0.0):
        if self._last_result is None:
            return
        self._render(self._last_result, offset_ms, consonant_ms, cutoff_ms,
                     overlap_ms, preutterance_ms, preserve_view=True)

    def _on_motion(self, event):
        if event.xdata is not None:
            self._last_xdata = event.xdata
        if self._pan_start is None or event.key is not None:
            return
        if not event.xdata:
            return
        if self._pan_last_xdata is None:
            return

        self._motion_count += 1
        # 增量位移：基于上一次 event.xdata，避免绝对偏移导致的抽搐
        dx_data = self._pan_last_xdata - event.xdata
        self._pan_last_xdata = event.xdata

        xlim = self.ax_wave.get_xlim()
        new_lo = xlim[0] + dx_data
        new_hi = xlim[1] + dx_data
        if new_lo < 0:
            new_hi -= new_lo
            new_lo = 0
        if new_hi > self._total_duration:
            new_lo -= (new_hi - self._total_duration)
            new_hi = self._total_duration
        if new_lo < 0:
            new_lo = 0

        self.ax_wave.set_xlim(new_lo, new_hi)
        if self._spec_times is not None:
            self.ax_spec.set_xlim(new_lo, new_hi)
        # 拖动期间直接 draw_idle，不节流、不 schedule，消除粘连感
        self.canvas.draw_idle()
