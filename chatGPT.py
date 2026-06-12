"""A desktop chat client for local LLMs served by Ollama.

A modern chat layout — a sidebar of saved conversations, a scrolling transcript
of message bubbles with Markdown/code rendering, and a composer at the bottom.
Model calls run on a background thread and stream their reply back through a
queue, so the window never freezes. Conversations and settings persist to disk.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog
from tkinter import font as tkfont
from tkinter import ttk

import mdrender
import requestLocal as backend
import storage

POLL_MS = 40

C = {
    "app_bg": "#0f1117",
    "sidebar": "#161922",
    "sidebar_active": "#232838",
    "sidebar_hover": "#1d2130",
    "header": "#161922",
    "chat_bg": "#0f1117",
    "composer": "#1b1f2b",
    "composer_border": "#2a3042",
    "bubble_user": "#3b6ef5",
    "bubble_user_fg": "#ffffff",
    "bubble_asst": "#1e2330",
    "bubble_asst_fg": "#e7e9ee",
    "text": "#e7e9ee",
    "muted": "#878da0",
    "faint": "#5b6273",
    "accent": "#3b6ef5",
    "accent_hover": "#2f5be0",
    "danger": "#e2554e",
    "danger_hover": "#c8453f",
    "border": "#242838",
    "code_bg": "#11141c",
    "code_fg": "#d7dce8",
    "code_header": "#0a0c12",
    "code_inline_fg": "#e6b673",
    "field": "#232838",
}


def _pick_family(root, *prefs):
    available = set(tkfont.families(root))
    for name in prefs:
        if name in available:
            return name
    return prefs[-1]


def fmt_size(num):
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


class Conversation:
    """One chat thread: its own page (transcript + composer) and history."""

    def __init__(self, app: "ChatApp", *, title="New chat", system="", model="", messages=None):
        self.app = app
        self.title = title or "New chat"
        self.system = system
        self.model = model
        self.messages: list[dict] = []

        self.queue: "queue.Queue" = queue.Queue()
        self.stop_event = threading.Event()
        self.generating = False
        self.current_response = ""
        self.meta: dict = {}

        self._asst_bubbles: list[dict] = []   # {"col","txt","frac"} for reflow
        self._user_labels: list[dict] = []     # {"label","frac"}
        self._rows: list[dict] = []            # ordered message rows
        self._stream = None                     # active assistant render target
        self.placeholder = None

        self.side_row = None
        self.side_label = None

        self._build_page()
        for m in (messages or []):
            self._render_message(m["role"], m["content"])
            self.messages.append({"role": m["role"], "content": m["content"]})
        if self.messages:
            self._clear_placeholder()
            self._refresh_actions()

    # ---- page construction ----------------------------------------------------

    def _build_page(self):
        self.page = tk.Frame(self.app.content, bg=C["chat_bg"])

        area = tk.Frame(self.page, bg=C["chat_bg"])
        area.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(area, bg=C["chat_bg"], highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview,
                               style="Chat.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)

        self.inner = tk.Frame(self.canvas, bg=C["chat_bg"])
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel())
        self.canvas.bind("<Leave>", lambda e: self._unbind_wheel())
        self._show_placeholder()

        bar = tk.Frame(self.page, bg=C["chat_bg"])
        bar.pack(side="bottom", fill="x", padx=18, pady=(6, 16))
        box = tk.Frame(bar, bg=C["composer"], highlightthickness=1,
                       highlightbackground=C["composer_border"], highlightcolor=C["accent"])
        box.pack(fill="x")

        self.send_btn = tk.Label(box, text="Send", bg=C["accent"], fg="#ffffff",
                                 font=self.app.fonts["bold"], padx=18, pady=8, cursor="hand2")
        self.send_btn.pack(side="right", padx=8, pady=8)
        self.send_btn.bind("<Button-1>", lambda e: self._on_action())
        self.app.hover(self.send_btn, C["accent"], C["accent_hover"])

        self.input = tk.Text(box, height=1, bg=C["composer"], fg=C["text"], wrap="word",
                             relief="flat", bd=0, padx=14, pady=12, insertbackground=C["text"],
                             font=self.app.fonts["body"], highlightthickness=0)
        self.input.pack(side="left", fill="both", expand=True)
        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.input.bind("<KeyRelease>", self._autosize_input)

    # ---- placeholder ----------------------------------------------------------

    def _show_placeholder(self):
        self.placeholder = tk.Frame(self.inner, bg=C["chat_bg"])
        self.placeholder.pack(fill="x", pady=(150, 0))
        tk.Label(self.placeholder, text="Ask anything", bg=C["chat_bg"], fg=C["text"],
                 font=self.app.fonts["title"]).pack()
        tk.Label(self.placeholder,
                 text="Your conversation stays on this machine, served locally by Ollama.",
                 bg=C["chat_bg"], fg=C["muted"], font=self.app.fonts["small"]).pack(pady=(6, 0))

    def _clear_placeholder(self):
        if self.placeholder is not None:
            self.placeholder.destroy()
            self.placeholder = None

    # ---- scrolling ------------------------------------------------------------

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._window, width=event.width)
        for b in self._user_labels:
            b["label"].configure(wraplength=max(220, int(event.width * b["frac"])))
        for b in self._asst_bubbles:
            self._fit_asst(b, precise=True)

    def _bind_wheel(self):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_wheel)

    def _unbind_wheel(self):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif abs(event.delta) >= 120:
            delta = -int(event.delta / 120)
        else:
            delta = -event.delta
        self.canvas.yview_scroll(delta, "units")
        return "break"

    def _near_bottom(self):
        try:
            return self.canvas.yview()[1] >= 0.999
        except tk.TclError:
            return True

    def _scroll_to_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)

    # ---- message rendering ----------------------------------------------------

    def _ypixels(self, txt):
        try:
            ypx = txt.count("1.0", "end-1c", "ypixels")
            if isinstance(ypx, tuple):
                ypx = ypx[0]
        except tk.TclError:
            ypx = None
        if not ypx:
            n = int(txt.index("end-1c").split(".")[0])
            ypx = n * self.app.fonts["body"].metrics("linespace")
        return ypx

    def _fit_asst(self, entry, precise=False):
        """Size the bubble to its content. `precise` measures the true bottom of
        the last line (needed when embedded code-block headers throw off the
        faster ypixels count); the fast path is used during streaming."""
        col, txt, frac = entry["col"], entry["txt"], entry["frac"]
        width = max(260, int(self.canvas.winfo_width() * frac))
        if precise:
            col.configure(width=width, height=6000)
            self.app.root.update_idletasks()
            info = txt.dlineinfo("end-1c")
            needed = (info[1] + info[3] + 16) if info else (self._ypixels(txt) + 22)
            col.configure(height=max(40, needed))
        else:
            col.configure(width=width)
            self.app.root.update_idletasks()
            col.configure(height=self._ypixels(txt) + 22)

    def _render_message(self, role, content):
        self._clear_placeholder()
        if role == "user":
            self._user_row(content)
        else:
            _, txt = self._assistant_row()
            mdrender.render(txt, content, fonts=self.app.fonts, palette=C,
                            copy_cb=self.app.copy_to_clipboard)
            txt.configure(state="disabled")
            self._rows[-1]["content"] = content
            self._fit_asst(self._asst_bubbles[-1], precise=True)

    def _user_row(self, text):
        row = tk.Frame(self.inner, bg=C["chat_bg"])
        row.pack(fill="x", padx=16, pady=(10, 0))
        col = tk.Frame(row, bg=C["chat_bg"])
        col.pack(side="right", anchor="e")
        tk.Label(col, text="You", bg=C["chat_bg"], fg=C["faint"],
                 font=self.app.fonts["caption"]).pack(anchor="e", padx=4, pady=(0, 2))
        frac = 0.72
        label = tk.Label(col, text=text, bg=C["bubble_user"], fg=C["bubble_user_fg"],
                         justify="left", anchor="w",
                         wraplength=max(220, int(self.canvas.winfo_width() * frac)),
                         font=self.app.fonts["body"], padx=14, pady=10)
        label.pack(anchor="e")
        self._user_labels.append({"label": label, "frac": frac})
        self._rows.append({"role": "user", "frame": row, "content": text})
        return row

    def _assistant_row(self):
        row = tk.Frame(self.inner, bg=C["chat_bg"])
        row.pack(fill="x", padx=16, pady=(10, 0))
        wrap = tk.Frame(row, bg=C["chat_bg"])
        wrap.pack(side="left", anchor="w")
        tk.Label(wrap, text=self.model or self.app.model_var.get() or "Assistant",
                 bg=C["chat_bg"], fg=C["faint"],
                 font=self.app.fonts["caption"]).pack(anchor="w", padx=4, pady=(0, 2))

        frac = 0.82
        col = tk.Frame(wrap, bg=C["bubble_asst"])
        col.pack(anchor="w")
        col.pack_propagate(False)
        txt = tk.Text(col, wrap="word", bd=0, highlightthickness=0, relief="flat",
                      bg=C["bubble_asst"], fg=C["bubble_asst_fg"], padx=14, pady=10,
                      font=self.app.fonts["body"], cursor="arrow")
        txt.pack(fill="both", expand=True)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            txt.bind(seq, self._on_wheel)
        mdrender.configure_tags(txt, self.app.fonts, C)

        actions = tk.Frame(wrap, bg=C["chat_bg"])
        actions.pack(anchor="w", pady=(2, 0))

        entry = {"col": col, "txt": txt, "frac": frac}
        self._asst_bubbles.append(entry)
        self._rows.append({"role": "assistant", "frame": row, "actions": actions,
                           "entry": entry, "content": ""})
        return row, txt

    def _refresh_actions(self):
        """Show Copy on every assistant row, Regenerate on the last one only."""
        asst_rows = [r for r in self._rows if r["role"] == "assistant"]
        for i, r in enumerate(asst_rows):
            for child in r["actions"].winfo_children():
                child.destroy()
            is_last = i == len(asst_rows) - 1

            copy = tk.Label(r["actions"], text="Copy", bg=C["chat_bg"], fg=C["faint"],
                            font=self.app.fonts["caption"], cursor="hand2")
            copy.pack(side="left", padx=(4, 10))
            copy.bind("<Button-1>", lambda e, row=r: self.app.copy_to_clipboard(row["content"]))
            self.app.hover_fg(copy, C["faint"], C["text"])
            if is_last and not self.generating:
                regen = tk.Label(r["actions"], text="↻ Regenerate", bg=C["chat_bg"],
                                 fg=C["faint"], font=self.app.fonts["caption"], cursor="hand2")
                regen.pack(side="left")
                regen.bind("<Button-1>", lambda e: self.regenerate())
                self.app.hover_fg(regen, C["faint"], C["text"])

    # ---- sending / streaming --------------------------------------------------

    def _on_return(self, _event):
        self._on_action()
        return "break"

    def _on_action(self):
        self.stop() if self.generating else self.send()

    def send(self):
        if self.generating:
            return
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        if not self.app.model_var.get().strip():
            self.app.set_status("No model selected — open Models to pull one")
            return
        self.input.delete("1.0", "end")
        self._autosize_input()
        self._render_message("user", text)
        self.messages.append({"role": "user", "content": text})
        if len([m for m in self.messages if m["role"] == "user"]) == 1:
            self.set_title(text)
        self._scroll_to_bottom()
        self._start_stream()
        self.app.schedule_save()

    def regenerate(self):
        if self.generating or not self.messages:
            return
        if self.messages[-1]["role"] != "assistant":
            return
        self.messages.pop()
        last = None
        for r in reversed(self._rows):
            if r["role"] == "assistant":
                last = r
                break
        if last is not None:
            self._rows.remove(last)
            if last.get("entry") in self._asst_bubbles:
                self._asst_bubbles.remove(last["entry"])
            last["frame"].destroy()
        self._start_stream()

    def _start_stream(self):
        model = self.app.model_var.get().strip()
        self.model = model
        self.generating = True
        self.stop_event.clear()
        self.current_response = ""
        self.meta = {}
        self._set_busy(True)
        self.app.set_status(f"{model} is thinking…")
        _, txt = self._assistant_row()
        self._stream = txt
        txt.insert("1.0", "…")
        self._fit_asst(self._asst_bubbles[-1])
        self._scroll_to_bottom()

        snapshot = []
        if self.system.strip():
            snapshot.append({"role": "system", "content": self.system})
        snapshot.extend(self.messages)
        options = {"temperature": self.app.temperature}
        threading.Thread(target=self._worker, args=(model, snapshot, options),
                         daemon=True).start()

    def _worker(self, model, messages, options):
        try:
            first = True
            for chunk in backend.chat_stream(model, messages, self.stop_event.is_set,
                                             options=options, meta=self.meta):
                self.queue.put(("first" if first else "chunk", chunk))
                first = False
        except backend.OllamaError as exc:
            self.queue.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover
            self.queue.put(("error", f"Unexpected error: {exc}"))
        finally:
            self.queue.put(("done", None))

    def drain(self):
        if not self.generating:
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind in ("first", "chunk"):
                    if kind == "first":
                        self._stream.delete("1.0", "end")  # clear the "…"
                    self.current_response += payload
                    stick = self._near_bottom()
                    self._stream.insert("end", payload)
                    self._fit_asst(self._asst_bubbles[-1])
                    if stick:
                        self._scroll_to_bottom()
                elif kind == "error":
                    self.current_response = ""
                    self._stream.delete("1.0", "end")
                    self._stream.insert("end", "⚠ " + payload)
                    self._stream.configure(bg="#2a1b1d", fg=C["danger"])
                    self.app.set_status("Error")
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass

    def _finish(self):
        text = self.current_response
        if text.strip():
            mdrender.render(self._stream, text, fonts=self.app.fonts, palette=C,
                            copy_cb=self.app.copy_to_clipboard)
            self.messages.append({"role": "assistant", "content": text})
            for r in reversed(self._rows):
                if r["role"] == "assistant":
                    r["content"] = text
                    break
            self._fit_asst(self._asst_bubbles[-1], precise=True)
        elif self._stream.get("1.0", "end").strip() in ("", "…"):
            self._stream.delete("1.0", "end")
            self._stream.insert("end", "(no response)")
            self._fit_asst(self._asst_bubbles[-1])
        self._stream.configure(state="disabled")
        self._stream = None
        self.generating = False
        self._set_busy(False)
        self._refresh_actions()
        self.app.set_status(self._stats_text())
        self.app.schedule_save()

    def _stats_text(self):
        ec, ed = self.meta.get("eval_count"), self.meta.get("eval_duration")
        if ec and ed:
            return f"{self.model} · {ec} tokens · {ec / (ed / 1e9):.0f} tok/s"
        return "Ready"

    def stop(self):
        if self.generating:
            self.stop_event.set()
            self.app.set_status("Stopping…")

    def clear(self):
        if self.generating:
            self.stop()
        self.messages.clear()
        self._asst_bubbles.clear()
        self._user_labels.clear()
        self._rows.clear()
        for child in self.inner.winfo_children():
            child.destroy()
        self.placeholder = None
        self._show_placeholder()
        self.app.schedule_save()

    def set_title(self, text):
        clean = " ".join(text.split())
        self.title = (clean[:30] + "…") if len(clean) > 31 else clean or "New chat"
        if self.side_label is not None:
            self.side_label.configure(text=self.title)
        if self.app.active is self:
            self.app.header_title.configure(text=self.title)
        self.app.schedule_save()

    def export_markdown(self):
        lines = [f"# {self.title}", ""]
        if self.system.strip():
            lines += ["> **System:** " + self.system, ""]
        for m in self.messages:
            who = "You" if m["role"] == "user" else (self.model or "Assistant")
            lines += [f"## {who}", "", m["content"], ""]
        return "\n".join(lines)

    # ---- widget state ---------------------------------------------------------

    def _set_busy(self, busy):
        if busy:
            self.send_btn.configure(text="Stop", bg=C["danger"])
            self.app.hover(self.send_btn, C["danger"], C["danger_hover"])
        else:
            self.send_btn.configure(text="Send", bg=C["accent"])
            self.app.hover(self.send_btn, C["accent"], C["accent_hover"])
            self.input.focus_set()

    def _autosize_input(self, _event=None):
        lines = int(self.input.index("end-1c").split(".")[0])
        self.input.configure(height=max(1, min(lines, 6)))

    def serialize(self):
        return {"title": self.title, "system": self.system, "model": self.model,
                "messages": self.messages}


class ChatApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = storage.load_settings()
        self.root.title("Local LLM Chat")
        self.root.geometry(self.settings.get("geometry", "1040x720"))
        self.root.minsize(760, 520)
        self.root.configure(bg=C["app_bg"])

        ui = _pick_family(root, "SF Pro Text", "Segoe UI", "Helvetica Neue", "Helvetica", "Arial")
        mono = _pick_family(root, "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Courier")
        self.fonts = {
            "title": tkfont.Font(family=ui, size=20, weight="bold"),
            "header": tkfont.Font(family=ui, size=14, weight="bold"),
            "bold": tkfont.Font(family=ui, size=13, weight="bold"),
            "body": tkfont.Font(family=ui, size=13),
            "italic": tkfont.Font(family=ui, size=13, slant="italic"),
            "bolditalic": tkfont.Font(family=ui, size=13, weight="bold", slant="italic"),
            "small": tkfont.Font(family=ui, size=11),
            "caption": tkfont.Font(family=ui, size=10),
            "mono": tkfont.Font(family=mono, size=12),
            "h1": tkfont.Font(family=ui, size=18, weight="bold"),
            "h2": tkfont.Font(family=ui, size=16, weight="bold"),
            "h3": tkfont.Font(family=ui, size=14, weight="bold"),
        }

        self.model_var = tk.StringVar(value=self.settings.get("default_model", ""))
        self.status_var = tk.StringVar(value="")
        self.temperature = float(self.settings.get("temperature", 0.7))
        self.conversations: list[Conversation] = []
        self.active: Conversation | None = None
        self._save_job = None

        self._setup_styles()
        self._build_ui()
        self.refresh_models()
        self._restore_conversations()
        self._bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(POLL_MS, self._poll)

    # ---- styling helpers ------------------------------------------------------

    def hover(self, widget, base, hover):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover))
        widget.bind("<Leave>", lambda e: widget.configure(bg=base))

    def hover_fg(self, widget, base, hover):
        widget.bind("<Enter>", lambda e: widget.configure(fg=hover))
        widget.bind("<Leave>", lambda e: widget.configure(fg=base))

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("Copied to clipboard")

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Chat.Vertical.TScrollbar", troughcolor=C["chat_bg"],
                        background=C["border"], bordercolor=C["chat_bg"],
                        arrowcolor=C["muted"], relief="flat", borderwidth=0)
        style.map("Chat.Vertical.TScrollbar", background=[("active", C["faint"])])
        style.configure("Model.TCombobox", fieldbackground=C["field"], background=C["field"],
                        foreground=C["text"], arrowcolor=C["text"], bordercolor=C["border"],
                        lightcolor=C["border"], darkcolor=C["border"], padding=5)
        style.map("Model.TCombobox",
                  fieldbackground=[("readonly", C["field"]), ("disabled", C["header"])],
                  foreground=[("readonly", C["text"]), ("disabled", C["faint"])],
                  background=[("readonly", C["field"])],
                  arrowcolor=[("readonly", C["text"]), ("disabled", C["faint"])],
                  selectbackground=[("readonly", C["field"])],
                  selectforeground=[("readonly", C["text"])])
        self.root.option_add("*TCombobox*Listbox.background", C["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.root.option_add("*TCombobox*Listbox.font", self.fonts["body"])

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=C["app_bg"])
        outer.pack(fill="both", expand=True)

        sidebar = tk.Frame(outer, bg=C["sidebar"], width=240)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=C["sidebar"])
        brand.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(brand, text="💬  Local Chat", bg=C["sidebar"], fg=C["text"],
                 font=self.fonts["header"]).pack(side="left")

        new_btn = tk.Label(sidebar, text="＋   New chat", bg=C["sidebar_active"], fg=C["text"],
                           font=self.fonts["bold"], padx=14, pady=10, cursor="hand2", anchor="w")
        new_btn.pack(fill="x", padx=12, pady=(4, 10))
        new_btn.bind("<Button-1>", lambda e: self.new_conversation())
        self.hover(new_btn, C["sidebar_active"], C["sidebar_hover"])

        self.side_list = tk.Frame(sidebar, bg=C["sidebar"])
        self.side_list.pack(fill="both", expand=True, padx=8)

        footer = tk.Frame(sidebar, bg=C["sidebar"])
        footer.pack(side="bottom", fill="x", pady=(4, 10), padx=8)
        for text, cmd in (("⚙  Settings", self.open_settings), ("⬢  Manage models", self.open_models)):
            item = tk.Label(footer, text=text, bg=C["sidebar"], fg=C["muted"],
                            font=self.fonts["body"], anchor="w", padx=10, pady=6, cursor="hand2")
            item.pack(fill="x")
            item.bind("<Button-1>", lambda e, c=cmd: c())
            self.hover_fg(item, C["muted"], C["text"])

        main = tk.Frame(outer, bg=C["app_bg"])
        main.pack(side="left", fill="both", expand=True)

        header = tk.Frame(main, bg=C["header"], height=58)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        self.header_title = tk.Label(header, text="New chat", bg=C["header"], fg=C["text"],
                                     font=self.fonts["header"], cursor="hand2")
        self.header_title.pack(side="left", padx=20)
        self.header_title.bind("<Double-Button-1>", lambda e: self._rename_active())

        refresh = tk.Label(header, text="↻", bg=C["header"], fg=C["muted"],
                           font=self.fonts["header"], cursor="hand2")
        refresh.pack(side="right", padx=(6, 16))
        refresh.bind("<Button-1>", lambda e: self.refresh_models())
        self.hover_fg(refresh, C["muted"], C["text"])
        self.model_combo = ttk.Combobox(header, textvariable=self.model_var, width=20,
                                        state="readonly", style="Model.TCombobox",
                                        font=self.fonts["body"])
        self.model_combo.pack(side="right", pady=12)
        self.model_combo.bind("<<ComboboxSelected>>", lambda e: self._on_model_change())
        tk.Label(header, text="Model", bg=C["header"], fg=C["muted"],
                 font=self.fonts["small"]).pack(side="right", padx=(0, 8))

        for text, cmd in (("Export", self._export_active), ("System", self.edit_system_prompt)):
            btn = tk.Label(header, text=text, bg=C["header"], fg=C["muted"],
                           font=self.fonts["body"], cursor="hand2", padx=8)
            btn.pack(side="right", padx=2)
            btn.bind("<Button-1>", lambda e, c=cmd: c())
            self.hover_fg(btn, C["muted"], C["text"])

        self.content = tk.Frame(main, bg=C["chat_bg"])
        self.content.pack(side="top", fill="both", expand=True)

        status = tk.Frame(main, bg=C["header"], height=26)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        tk.Label(status, textvariable=self.status_var, bg=C["header"], fg=C["muted"],
                 font=self.fonts["small"]).pack(side="left", padx=20)

    # ---- conversation management ----------------------------------------------

    def _restore_conversations(self):
        for data in storage.load_conversations():
            conv = Conversation(self, title=data.get("title", "New chat"),
                                system=data.get("system", ""), model=data.get("model", ""),
                                messages=data.get("messages", []))
            self.conversations.append(conv)
            self._add_sidebar_row(conv)
        if self.conversations:
            self.show(self.conversations[0])
        else:
            self.new_conversation()

    def new_conversation(self):
        conv = Conversation(self, system=self.settings.get("system_prompt", ""),
                            model=self.model_var.get())
        self.conversations.insert(0, conv)
        self._add_sidebar_row(conv, at_top=True)
        self.show(conv)
        conv.input.focus_set()
        self.schedule_save()

    def _add_sidebar_row(self, conv, at_top=False):
        existing = self.side_list.winfo_children()
        row = tk.Frame(self.side_list, bg=C["sidebar"])
        row.pack(fill="x", pady=2)
        if at_top and existing:
            row.pack_configure(before=existing[0])
        label = tk.Label(row, text=conv.title, bg=C["sidebar"], fg=C["muted"],
                         font=self.fonts["body"], anchor="w", padx=10, pady=8, cursor="hand2")
        label.pack(side="left", fill="x", expand=True)
        delete = tk.Label(row, text="✕", bg=C["sidebar"], fg=C["faint"],
                          font=self.fonts["small"], padx=8, cursor="hand2")
        delete.pack(side="right")
        conv.side_row = row
        conv.side_label = label
        for w in (row, label):
            w.bind("<Button-1>", lambda e, c=conv: self.show(c))
        label.bind("<Double-Button-1>", lambda e, c=conv: self._rename(c))
        delete.bind("<Button-1>", lambda e, c=conv: self.delete_conversation(c))
        self.hover_fg(delete, C["faint"], C["danger"])
        self._style_sidebar()

    def show(self, conv):
        if self.active is not None and self.active is not conv:
            self.active.page.pack_forget()
        self.active = conv
        conv.page.pack(fill="both", expand=True)
        self.header_title.configure(text=conv.title)
        if conv.model:
            models = list(self.model_combo["values"])
            if conv.model in models:
                self.model_var.set(conv.model)
        self._style_sidebar()
        conv.input.focus_set()

    def delete_conversation(self, conv):
        if len(self.conversations) <= 1:
            conv.clear()
            conv.set_title("New chat")
            self.set_status("That's the last chat — cleared it instead.")
            return
        conv.stop()
        was_active = self.active is conv
        idx = self.conversations.index(conv)
        conv.page.destroy()
        conv.side_row.destroy()
        self.conversations.remove(conv)
        if was_active:
            self.active = None
            self.show(self.conversations[min(idx, len(self.conversations) - 1)])
        else:
            self._style_sidebar()
        self.schedule_save()

    def _style_sidebar(self):
        for conv in self.conversations:
            active = conv is self.active
            bg = C["sidebar_active"] if active else C["sidebar"]
            conv.side_row.configure(bg=bg)
            conv.side_label.configure(bg=bg, fg=C["text"] if active else C["muted"])
            for child in conv.side_row.winfo_children():
                if child is not conv.side_label:
                    child.configure(bg=bg)

    def _rename_active(self):
        if self.active:
            self._rename(self.active)

    def _rename(self, conv):
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename chat")
        dialog.configure(bg=C["app_bg"])
        dialog.transient(self.root)
        tk.Label(dialog, text="Conversation name", bg=C["app_bg"], fg=C["text"],
                 font=self.fonts["body"]).pack(padx=16, pady=(16, 6), anchor="w")
        var = tk.StringVar(value=conv.title)
        entry = tk.Entry(dialog, textvariable=var, bg=C["field"], fg=C["text"],
                         insertbackground=C["text"], relief="flat", font=self.fonts["body"], width=34)
        entry.pack(padx=16, fill="x")
        entry.focus_set()
        entry.select_range(0, "end")

        def commit(_e=None):
            name = var.get().strip()
            if name:
                conv.title = (name[:40])
                conv.side_label.configure(text=conv.title)
                if self.active is conv:
                    self.header_title.configure(text=conv.title)
                self.schedule_save()
            dialog.destroy()

        entry.bind("<Return>", commit)
        btns = tk.Frame(dialog, bg=C["app_bg"])
        btns.pack(padx=16, pady=16, anchor="e")
        self._dialog_button(btns, "Save", commit, accent=True).pack(side="right")
        self._dialog_button(btns, "Cancel", dialog.destroy).pack(side="right", padx=(0, 8))
        self._center(dialog)

    # ---- system prompt / export -----------------------------------------------

    def edit_system_prompt(self):
        if not self.active:
            return
        conv = self.active
        dialog = tk.Toplevel(self.root)
        dialog.title("System prompt")
        dialog.configure(bg=C["app_bg"])
        dialog.transient(self.root)
        tk.Label(dialog, text=f"System prompt for “{conv.title}”", bg=C["app_bg"], fg=C["text"],
                 font=self.fonts["bold"]).pack(padx=16, pady=(16, 4), anchor="w")
        tk.Label(dialog, text="Steers the model for this conversation. Leave blank for none.",
                 bg=C["app_bg"], fg=C["muted"], font=self.fonts["small"]).pack(padx=16, anchor="w")
        text = tk.Text(dialog, width=58, height=8, bg=C["field"], fg=C["text"], wrap="word",
                       insertbackground=C["text"], relief="flat", font=self.fonts["body"],
                       padx=10, pady=8)
        text.pack(padx=16, pady=10, fill="both", expand=True)
        text.insert("1.0", conv.system)
        text.focus_set()

        def commit():
            conv.system = text.get("1.0", "end").strip()
            self.schedule_save()
            self.set_status("System prompt updated")
            dialog.destroy()

        btns = tk.Frame(dialog, bg=C["app_bg"])
        btns.pack(padx=16, pady=(0, 16), anchor="e")
        self._dialog_button(btns, "Save", commit, accent=True).pack(side="right")
        self._dialog_button(btns, "Cancel", dialog.destroy).pack(side="right", padx=(0, 8))
        self._center(dialog)

    def _export_active(self):
        if not self.active or not self.active.messages:
            self.set_status("Nothing to export yet")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Text", "*.txt")],
            initialfile=f"{self.active.title[:40] or 'chat'}.md")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.active.export_markdown())
            self.set_status(f"Exported to {path}")
        except OSError as exc:
            self.set_status(f"Export failed: {exc}")

    # ---- settings & model manager ---------------------------------------------

    def open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.configure(bg=C["app_bg"])
        dialog.transient(self.root)
        pad = {"padx": 18, "anchor": "w"}

        tk.Label(dialog, text="Settings", bg=C["app_bg"], fg=C["text"],
                 font=self.fonts["title"]).pack(pady=(16, 10), **pad)

        tk.Label(dialog, text="Default model for new chats", bg=C["app_bg"], fg=C["text"],
                 font=self.fonts["body"]).pack(pady=(6, 2), **pad)
        model_var = tk.StringVar(value=self.settings.get("default_model", ""))
        models = backend.list_models()
        combo = ttk.Combobox(dialog, textvariable=model_var, values=models, state="readonly",
                             style="Model.TCombobox", width=30, font=self.fonts["body"])
        combo.pack(padx=18, fill="x")

        tk.Label(dialog, text="Default system prompt", bg=C["app_bg"], fg=C["text"],
                 font=self.fonts["body"]).pack(pady=(12, 2), **pad)
        sys_text = tk.Text(dialog, width=48, height=4, bg=C["field"], fg=C["text"], wrap="word",
                           insertbackground=C["text"], relief="flat", font=self.fonts["body"],
                           padx=10, pady=8)
        sys_text.pack(padx=18, fill="x")
        sys_text.insert("1.0", self.settings.get("system_prompt", ""))

        temp_var = tk.DoubleVar(value=self.temperature)
        temp_label = tk.Label(dialog, text=f"Temperature: {self.temperature:.2f}", bg=C["app_bg"],
                              fg=C["text"], font=self.fonts["body"])
        temp_label.pack(pady=(12, 2), **pad)
        scale = ttk.Scale(dialog, from_=0.0, to=1.5, variable=temp_var, orient="horizontal",
                          command=lambda v: temp_label.configure(text=f"Temperature: {float(v):.2f}"))
        scale.pack(padx=18, fill="x")

        def commit():
            self.settings["default_model"] = model_var.get()
            self.settings["system_prompt"] = sys_text.get("1.0", "end").strip()
            self.settings["temperature"] = round(float(temp_var.get()), 2)
            self.temperature = self.settings["temperature"]
            storage.save_settings(self.settings)
            self.set_status("Settings saved")
            dialog.destroy()

        btns = tk.Frame(dialog, bg=C["app_bg"])
        btns.pack(padx=18, pady=18, anchor="e", fill="x")
        self._dialog_button(btns, "Save", commit, accent=True).pack(side="right")
        self._dialog_button(btns, "Cancel", dialog.destroy).pack(side="right", padx=(0, 8))
        self._center(dialog)

    def open_models(self):
        ModelManager(self)

    # ---- model list -----------------------------------------------------------

    def refresh_models(self):
        models = backend.list_models()
        if models:
            self.model_combo.configure(values=models, state="readonly")
            if self.model_var.get() not in models:
                self.model_var.set(models[0])
            self.set_status(f"{len(models)} model(s) installed · {self.model_var.get()}")
        else:
            self.model_combo.configure(values=[], state="disabled")
            self.model_var.set("")
            if backend.is_running():
                self.set_status("No models installed — open Manage models to pull one")
            else:
                self.set_status("Ollama not reachable — start it with 'ollama serve', then ↻")

    def _on_model_change(self):
        if self.active:
            self.active.model = self.model_var.get()
            self.schedule_save()

    # ---- shortcuts / lifecycle ------------------------------------------------

    def _bind_shortcuts(self):
        for mod in ("Command", "Control"):
            self.root.bind_all(f"<{mod}-n>", lambda e: (self.new_conversation(), "break")[1])
            self.root.bind_all(f"<{mod}-e>", lambda e: (self._export_active(), "break")[1])
            self.root.bind_all(f"<{mod}-r>", lambda e: (self._regen_active(), "break")[1])
            self.root.bind_all(f"<{mod}-comma>", lambda e: (self.open_settings(), "break")[1])
        self.root.bind_all("<Escape>", lambda e: self.active.stop() if self.active else None)

    def _regen_active(self):
        if self.active:
            self.active.regenerate()

    def set_status(self, text):
        self.status_var.set(text)

    def schedule_save(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(600, self._save_now)

    def _save_now(self):
        self._save_job = None
        storage.save_conversations([c.serialize() for c in self.conversations])

    def _on_close(self):
        try:
            self.settings["geometry"] = self.root.winfo_geometry()
            storage.save_settings(self.settings)
            storage.save_conversations([c.serialize() for c in self.conversations])
        finally:
            self.root.destroy()

    def _poll(self):
        if not self.root.winfo_exists():
            return
        for conv in self.conversations:
            conv.drain()
        self.root.after(POLL_MS, self._poll)

    # ---- small dialog helpers -------------------------------------------------

    def _dialog_button(self, parent, text, command, accent=False):
        btn = tk.Label(parent, text=text, bg=C["accent"] if accent else C["field"],
                       fg="#ffffff" if accent else C["text"], font=self.fonts["bold"],
                       padx=16, pady=7, cursor="hand2")
        btn.bind("<Button-1>", lambda e: command())
        self.hover(btn, C["accent"] if accent else C["field"],
                   C["accent_hover"] if accent else C["sidebar_hover"])
        return btn

    def _center(self, dialog):
        dialog.update_idletasks()
        w, h = dialog.winfo_width(), dialog.winfo_height()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 3
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()


class ModelManager:
    """Toplevel for listing, deleting, and pulling models with progress."""

    def __init__(self, app: ChatApp):
        self.app = app
        self.queue: "queue.Queue" = queue.Queue()
        self.pulling = False

        self.win = tk.Toplevel(app.root)
        self.win.title("Manage models")
        self.win.configure(bg=C["app_bg"])
        self.win.geometry("520x520")
        self.win.transient(app.root)

        tk.Label(self.win, text="Manage models", bg=C["app_bg"], fg=C["text"],
                 font=app.fonts["title"]).pack(padx=18, pady=(16, 8), anchor="w")

        pull = tk.Frame(self.win, bg=C["app_bg"])
        pull.pack(fill="x", padx=18, pady=(0, 8))
        self.entry = tk.Entry(pull, bg=C["field"], fg=C["text"], insertbackground=C["text"],
                              relief="flat", font=app.fonts["body"])
        self.entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.entry.insert(0, "")
        self.entry.bind("<Return>", lambda e: self.pull())
        self.pull_btn = app._dialog_button(pull, "Pull", self.pull, accent=True)
        self.pull_btn.pack(side="right")
        tk.Label(self.win, text="e.g. llama3.1:8b, qwen2.5-coder:7b, phi3 — from ollama.com/library",
                 bg=C["app_bg"], fg=C["muted"], font=app.fonts["small"]).pack(padx=18, anchor="w")

        self.progress = ttk.Progressbar(self.win, mode="determinate", maximum=100)
        self.progress_label = tk.Label(self.win, text="", bg=C["app_bg"], fg=C["muted"],
                                       font=app.fonts["small"])

        tk.Label(self.win, text="Installed", bg=C["app_bg"], fg=C["text"],
                 font=app.fonts["bold"]).pack(padx=18, pady=(14, 4), anchor="w")
        self.list_frame = tk.Frame(self.win, bg=C["app_bg"])
        self.list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        self._reload()
        app._center(self.win)
        self.win.after(80, self._drain)

    def _reload(self):
        for child in self.list_frame.winfo_children():
            child.destroy()
        models = backend.list_models_detailed()
        if not models:
            tk.Label(self.list_frame, text="No models installed yet.", bg=C["app_bg"],
                     fg=C["muted"], font=self.app.fonts["body"]).pack(anchor="w", pady=8)
            return
        for m in models:
            row = tk.Frame(self.list_frame, bg=C["sidebar"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=m["name"], bg=C["sidebar"], fg=C["text"],
                     font=self.app.fonts["body"], anchor="w", padx=12, pady=8).pack(side="left")
            tk.Label(row, text=fmt_size(m["size"]), bg=C["sidebar"], fg=C["muted"],
                     font=self.app.fonts["small"]).pack(side="left", padx=8)
            dele = tk.Label(row, text="Delete", bg=C["sidebar"], fg=C["faint"],
                            font=self.app.fonts["small"], cursor="hand2", padx=12)
            dele.pack(side="right")
            dele.bind("<Button-1>", lambda e, name=m["name"]: self._delete(name))
            self.app.hover_fg(dele, C["faint"], C["danger"])

    def _delete(self, name):
        try:
            backend.delete_model(name)
            self.app.set_status(f"Deleted {name}")
        except backend.OllamaError as exc:
            self.app.set_status(str(exc))
        self._reload()
        self.app.refresh_models()

    def pull(self):
        name = self.entry.get().strip()
        if not name or self.pulling:
            return
        self.pulling = True
        self.progress.pack(fill="x", padx=18, pady=(6, 0))
        self.progress_label.pack(padx=18, anchor="w")
        self.progress_label.configure(text=f"Pulling {name}…")
        self.progress.configure(value=0)
        threading.Thread(target=self._pull_worker, args=(name,), daemon=True).start()

    def _pull_worker(self, name):
        try:
            backend.pull_model(name, lambda u: self.queue.put(("progress", u)))
            self.queue.put(("done", name))
        except backend.OllamaError as exc:
            self.queue.put(("error", str(exc)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    total, done = payload.get("total", 0), payload.get("completed", 0)
                    status = payload.get("status", "")
                    if total:
                        pct = done / total * 100
                        self.progress.configure(value=pct)
                        self.progress_label.configure(
                            text=f"{status} — {fmt_size(done)} / {fmt_size(total)} ({pct:.0f}%)")
                    else:
                        self.progress_label.configure(text=status)
                elif kind == "done":
                    self.pulling = False
                    self.progress.configure(value=100)
                    self.progress_label.configure(text=f"Pulled {payload} ✓")
                    self.entry.delete(0, "end")
                    self._reload()
                    self.app.refresh_models()
                elif kind == "error":
                    self.pulling = False
                    self.progress_label.configure(text=payload, fg=C["danger"])
        except queue.Empty:
            pass
        if self.win.winfo_exists():
            self.win.after(120, self._drain)


def main():
    root = tk.Tk()
    ChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
