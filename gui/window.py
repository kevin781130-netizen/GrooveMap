"""Tkinter GUI (規格 8) — 簡單優先。"""
from __future__ import annotations
import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core.pipeline import Pipeline, AnalysisResult
from core.tempo_factor import apply_tempo_factor
from core.alignment import apply_alignment, MIN_OFFSET_MS, MAX_OFFSET_MS
from exporter.midi import export_cubase_bundle


class GrooveMapApp:
    SR_PRESETS = [
        ("44.1 kHz（標準，預設）", 44100),
        ("48 kHz / 24bit（Live 錄音常用）", 48000),
        ("22.05 kHz（快速分析）", 22050),
    ]

    DENSITY_LABELS = [
        ("Sparse（少量控制點）", "sparse"),
        ("Balanced（預設，平衡）", "balanced"),
        ("Detailed（保留較多細節）", "detailed"),
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("GrooveMap  —  Live Band Tempo Mapping")
        self.root.geometry("680x560")
        self.root.minsize(620, 500)

        self.result = None
        self.analysis_result = None  # 分析出來的原始結果，套用 tempo factor 前的 Ground Truth
        self.worker = None
        self._cancel_flag = False
        self.q = queue.Queue()

        self._build_ui()
        self._poll()

    def _build_ui(self):
        pad = dict(padx=10, pady=6)
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        box1 = ttk.LabelFrame(main, text="1. 選擇音檔")
        box1.pack(fill="x", **pad)
        self.file_var = tk.StringVar()
        ttk.Entry(box1, textvariable=self.file_var).pack(side="left", fill="x", expand=True, padx=(8, 4), pady=8)
        ttk.Button(box1, text="瀏覽…", command=self._browse).pack(side="left", padx=4, pady=8)
        ttk.Button(box1, text="清除", command=lambda: self.file_var.set("")).pack(side="left", padx=(0, 8), pady=8)

        box2 = ttk.LabelFrame(main, text="2. 分析設定")
        box2.pack(fill="x", **pad)
        r1 = ttk.Frame(box2)
        r1.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(r1, text="起始 BPM:").pack(side="left")
        self.bpm_var = tk.StringVar(value="120")
        ttk.Spinbox(r1, from_=40, to=300, width=6, textvariable=self.bpm_var).pack(side="left", padx=(4, 18))

        ttk.Label(r1, text="拍號:").pack(side="left")
        self.meter_var = tk.StringVar(value="4/4")
        ttk.Combobox(r1, width=6, state="readonly", textvariable=self.meter_var,
                     values=["3/4", "4/4", "6/8", "12/8"]).pack(side="left", padx=(4, 18))

        ttk.Label(r1, text="平滑強度:").pack(side="left")
        self.smooth_var = tk.DoubleVar(value=0.6)
        ttk.Scale(r1, from_=0.0, to=1.0, variable=self.smooth_var, length=130).pack(side="left", padx=4)

        r2 = ttk.Frame(box2)
        r2.pack(fill="x", padx=8, pady=(0, 8))
        self.demucs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r2, text="使用 Demucs 分離鼓軌（較慢）", variable=self.demucs_var).pack(side="left")
        ttk.Label(r2, text="首次使用需保持網路連線以下載模型（約數百 MB）",
                  foreground="#888888").pack(side="left", padx=(10, 0))

        r3 = ttk.Frame(box2)
        r3.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(r3, text="取樣率:").pack(side="left")
        self.sr_var = tk.StringVar(value=self.SR_PRESETS[0][0])
        ttk.Combobox(r3, width=26, state="readonly", textvariable=self.sr_var,
                     values=[label for label, _ in self.SR_PRESETS]).pack(side="left", padx=(4, 0))

        ttk.Label(r3, text="Tempo Density:").pack(side="left", padx=(18, 0))
        self.density_var = tk.StringVar(value=self.DENSITY_LABELS[1][0])
        ttk.Combobox(r3, width=22, state="readonly", textvariable=self.density_var,
                     values=[label for label, _ in self.DENSITY_LABELS]).pack(side="left", padx=(4, 0))

        r3b = ttk.Frame(box2)
        r3b.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(r3b, text="Max Tempo Nodes（0 = 用 Density 預設值）:").pack(side="left")
        self.max_nodes_var = tk.StringVar(value="0")
        ttk.Spinbox(r3b, from_=0, to=2000, width=6, textvariable=self.max_nodes_var).pack(side="left", padx=(4, 0))

        r4 = ttk.Frame(box2)
        r4.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(r4, text="Tempo 校正:").pack(side="left")
        self.tempo_factor_var = tk.StringVar(value="1x（原始偵測）")
        self.tempo_factor_combo = ttk.Combobox(
            r4, width=16, state="readonly", textvariable=self.tempo_factor_var,
            values=["1x（原始偵測）", "2x（Double Tempo）", "0.5x（Half Tempo）"])
        self.tempo_factor_combo.pack(side="left", padx=(4, 10))
        self.tempo_factor_combo.bind("<<ComboboxSelected>>", lambda e: self._recompute_result())
        ttk.Label(r4, text="分析完成後才能切換，依耳朵判斷偵測是否抓成雙倍/一半速度",
                  foreground="#888888").pack(side="left")

        box2b = ttk.LabelFrame(main, text="2b. Bar Alignment（分析完成後可調整）")
        box2b.pack(fill="x", **pad)
        r5 = ttk.Frame(box2b)
        r5.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(r5, text="First Beat Offset (ms):").pack(side="left")
        self.offset_var = tk.IntVar(value=0)
        offset_scale = ttk.Scale(r5, from_=MIN_OFFSET_MS, to=MAX_OFFSET_MS, orient="horizontal",
                                  variable=self.offset_var, length=220,
                                  command=lambda v: self._on_offset_dragging())
        offset_scale.pack(side="left", padx=(4, 8))
        offset_scale.bind("<ButtonRelease-1>", lambda e: self._recompute_result())
        self.offset_label_var = tk.StringVar(value="0 ms")
        ttk.Label(r5, textvariable=self.offset_label_var, width=8).pack(side="left")

        r6 = ttk.Frame(box2b)
        r6.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(r6, text='指定 "This is Bar 1 Beat 1"（輸入結果列表裡的 #beat 編號）:').pack(side="left")
        self.manual_downbeat_var = tk.StringVar(value="")
        ttk.Entry(r6, width=6, textvariable=self.manual_downbeat_var).pack(side="left", padx=(4, 8))
        ttk.Button(r6, text="套用", command=self._recompute_result).pack(side="left")
        ttk.Button(r6, text="清除手動指定", command=self._clear_manual_downbeat).pack(side="left", padx=(6, 0))

        act = ttk.Frame(main)
        act.pack(fill="x", **pad)
        self.analyze_btn = ttk.Button(act, text="開始分析", command=self._analyze)
        self.analyze_btn.pack(side="left")
        self.export_btn = ttk.Button(act, text="Export Cubase", command=self._export, state="disabled")
        self.export_btn.pack(side="left", padx=8)
        self.cancel_btn = ttk.Button(act, text="取消", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left")

        prog = ttk.Frame(main)
        prog.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(prog, mode="determinate", maximum=1000)
        self.progress.pack(fill="x")
        self.status_var = tk.StringVar(value="待機中")
        ttk.Label(prog, textvariable=self.status_var).pack(anchor="w", pady=(4, 0))

        box3 = ttk.LabelFrame(main, text="3. 分析結果")
        box3.pack(fill="both", expand=True, **pad)
        self.result_text = tk.Text(box3, height=10, state="disabled", wrap="word", font=("Consolas", 10))
        self.result_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="選擇 Live 錄音檔",
            filetypes=[("音訊檔", "*.wav *.aif *.aiff *.flac *.mp3 *.ogg *.m4a"),
                       ("WAV", "*.wav"), ("AIFF", "*.aif *.aiff"), ("所有檔案", "*.*")])
        if path:
            self.file_var.set(path)

    def _analyze(self):
        path = self.file_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("GrooveMap", "請先選擇有效的音檔。")
            return
        if self.worker and self.worker.is_alive():
            return

        self._cancel_flag = False
        self.result = None
        self.analysis_result = None
        self.tempo_factor_var.set("1x（原始偵測）")
        self.offset_var.set(0)
        self.offset_label_var.set("0 ms")
        self.manual_downbeat_var.set("")
        self.export_btn.config(state="disabled")
        self.analyze_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress["value"] = 0
        self.status_var.set("準備中…")
        self._set_text("")

        opts = dict(
            start_bpm=self._to_float(self.bpm_var.get(), 120.0),
            beats_per_bar=self._beats_per_bar(),
            smooth_strength=float(self.smooth_var.get()),
            use_demucs=bool(self.demucs_var.get()),
            sr=self._selected_sr(),
            tempo_density=self._selected_density(),
            max_tempo_nodes=self._max_nodes_override(),
        )
        self.worker = threading.Thread(target=self._run_worker, args=(path, opts), daemon=True)
        self.worker.start()

    def _run_worker(self, path, opts):
        try:
            pipe = Pipeline(opts)
            res = pipe.run(path, progress=lambda f, m: self.q.put(("progress", (f, m))),
                           cancel=lambda: self._cancel_flag)
            self.q.put(("done", res))
        except Exception as exc:
            self.q.put(("error", f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"))

    def _cancel(self):
        self._cancel_flag = True
        self.status_var.set("取消中…")

    def _export(self):
        if self.result is None:
            return
        base = os.path.splitext(os.path.basename(self.result.path))[0]
        out_dir = filedialog.askdirectory(title="選擇 MIDI 輸出資料夾")
        if not out_dir:
            return
        if not os.access(out_dir, os.W_OK):
            messagebox.showerror("GrooveMap",
                f"沒有寫入權限：\n{out_dir}\n\n請選擇其他資料夾（避免系統保護的目錄，如 C 槽根目錄）。")
            return
        try:
            files = export_cubase_bundle(self.result, out_dir, base)
        except PermissionError as exc:
            messagebox.showerror("GrooveMap", f"匯出失敗（權限不足）：\n{exc}\n\n請選擇其他資料夾。")
            return
        except Exception as exc:
            messagebox.showerror("GrooveMap", f"匯出失敗：\n{exc}")
            return
        lines = "\n".join(f"  {k:8s} →  {v}" for k, v in files.items())
        messagebox.showinfo("GrooveMap",
            "已輸出以下檔案：\n\n" + lines +
            "\n\nTempo Track：在 Cubase 匯入 *_MasterTrack.smt"
            "\nClick/Marker：匯入 *_Cubase.mid")

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "progress":
                    frac, msg = payload
                    self.progress["value"] = frac * 1000
                    self.status_var.set(msg)
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "error":
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _on_done(self, result):
        self.analysis_result = result
        self.result = result
        self.analyze_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.export_btn.config(state="normal")
        self.progress["value"] = 1000
        self.status_var.set("分析完成 ✓")

        if result.demucs_warning:
            messagebox.showwarning("GrooveMap", result.demucs_warning)

        self._render_result(result)

    def _on_offset_dragging(self):
        self.offset_label_var.set(f"{int(self.offset_var.get())} ms")

    def _clear_manual_downbeat(self):
        self.manual_downbeat_var.set("")
        self._recompute_result()

    def _recompute_result(self, _event=None):
        """從分析當下的原始結果開始，依序套用 Tempo 校正（Half/Double）→
        Bar Alignment（First Beat Offset + 手動指定 Bar1 Beat1），
        確保所有後續調整都疊在同一份 Ground Truth 上，不會互相打架。"""
        if self.analysis_result is None:
            return

        result = self.analysis_result

        label = self.tempo_factor_var.get()
        factor = {"1x（原始偵測）": 1.0, "2x（Double Tempo）": 2.0, "0.5x（Half Tempo）": 0.5}.get(label, 1.0)
        try:
            if factor != 1.0:
                result = apply_tempo_factor(result, factor)

            offset_ms = float(self.offset_var.get())
            manual_beat = self._manual_downbeat_beat_number()
            if offset_ms != 0.0 or manual_beat is not None:
                result = apply_alignment(
                    result, first_beat_offset_ms=offset_ms,
                    manual_downbeat_beat_number=manual_beat)
        except Exception as exc:
            messagebox.showerror("GrooveMap", f"套用校正失敗：\n{exc}")
            return

        self.result = result
        self.status_var.set("已套用校正")
        self._render_result(result)

    def _manual_downbeat_beat_number(self):
        s = self.manual_downbeat_var.get().strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def _render_result(self, result):
        s = result.summary()
        lines = [
            f"檔案名稱 : {s['檔案']}",
            f"長度     : {s['長度']}",
            f"整體 BPM : {s['整體 BPM']}",
            f"Beat 數  : {s['Beat 數']}",
            f"小節數   : {s['小節數']}",
            f"拍號     : {s['拍號']}",
            f"Demucs   : {s['Demucs']}",
        ]
        if result.demucs_warning:
            lines.append(f"⚠ {result.demucs_warning}")

        if result.accuracy_report is not None:
            ar = result.accuracy_report
            lines += [
                "",
                "── Accuracy Report ──",
                f"  Tempo Density      : {getattr(result, 'tempo_density', 'balanced')}"
                + (f"（Max Nodes={result.max_tempo_nodes}）" if getattr(result, "max_tempo_nodes", None) else ""),
                f"  Average Beat Error : {ar.avg_error_ms:6.1f} ms  ({ar.quality_label})",
                f"  Maximum Beat Error : {ar.max_error_ms:6.1f} ms",
                f"  Tempo Points       : {ar.num_points} / {ar.num_beats}",
                f"  Density            : {ar.density_label}",
            ]

        lines += [
            "",
            "── 前 12 拍（秒 / BPM，Ground Truth，未平滑）──",
        ]
        n = min(12, result.beat_count)
        dbs = set(result.downbeats.tolist())
        for i in range(n):
            t = result.beat_times[i]
            b = result.bpm_raw[i]
            mark = "  ▎小節" if i in dbs else ""
            lines.append(f"  #{i + 1:04d}   {t:8.3f}s    {b:7.2f} BPM{mark}")
        self._set_text("\n".join(lines))

    def _on_error(self, msg):
        self.analyze_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.status_var.set("分析失敗")
        self._set_text(msg)
        messagebox.showerror("GrooveMap", msg.split("\n\n")[0])

    def _set_text(self, text):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        if text:
            self.result_text.insert("1.0", text)
        self.result_text.config(state="disabled")

    def _beats_per_bar(self):
        try:
            return int(self.meter_var.get().split("/")[0])
        except Exception:
            return 4

    def _selected_sr(self):
        label = self.sr_var.get()
        for l, sr in self.SR_PRESETS:
            if l == label:
                return sr
        return 44100

    def _selected_density(self):
        label = self.density_var.get()
        for l, key in self.DENSITY_LABELS:
            if l == label:
                return key
        return "balanced"

    def _max_nodes_override(self):
        try:
            n = int(self.max_nodes_var.get())
        except (TypeError, ValueError):
            return None
        return n if n > 0 else None

    @staticmethod
    def _to_float(s, default):
        try:
            return float(s)
        except Exception:
            return default


def launch():
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except Exception:
        pass
    GrooveMapApp(root)
    root.mainloop()
