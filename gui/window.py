"""Tkinter GUI (規格 8) — 簡單優先。"""
from __future__ import annotations
import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core.pipeline import Pipeline, AnalysisResult
from exporter.midi import export_cubase_bundle


class GrooveMapApp:
    SR_PRESETS = [
        ("44.1 kHz（標準，預設）", 44100),
        ("48 kHz / 24bit（Live 錄音常用）", 48000),
        ("22.05 kHz（快速分析）", 22050),
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("GrooveMap  —  Live Band Tempo Mapping")
        self.root.geometry("680x560")
        self.root.minsize(620, 500)

        self.result = None
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
            "已輸出以下 MIDI 檔：\n\n" + lines +
            "\n\n在 Cubase 匯入 *Cubase.mid 即可。")

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
        self.result = result
        self.analyze_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self.export_btn.config(state="normal")
        self.progress["value"] = 1000
        self.status_var.set("分析完成 ✓")

        if result.demucs_warning:
            messagebox.showwarning("GrooveMap", result.demucs_warning)

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
        lines += [
            "",
            "── 前 12 拍（秒 / BPM）──",
        ]
        n = min(12, result.beat_count)
        dbs = set(result.downbeats.tolist())
        for i in range(n):
            t = result.beat_times[i]
            b = result.bpm_smooth[i]
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
