"""A small desktop chat client for local LLMs served by Ollama.

The UI is a modern chat layout: a sidebar of conversations on the left, a
scrolling transcript of message bubbles in the middle, and a composer at the
bottom. Every model call runs on a background thread and streams its reply back
to the UI through a queue, so the window never freezes and text appears as it's
generated. Each conversation keeps its own history, so the model has context.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import requestLocal as backend

POLL_MS = 40  # how often the UI drains worker output

# A flat, modern dark palette.
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
}


def _pick_family(root, *preferences):
    """Return the first installed font family from preferences, else a default."""
    available = set(tkfont.families(root))
    for name in preferences:
        if name in available:
            return name
    return preferences[-1]


class Conversation:
    """One chat thread: its own page (transcript + composer) and history."""

    def __init__(self, app: "ChatApp"):
        self.app = app
        self.title = "New chat"
        self.messages: list[dict] = []
        self.queue: "queue.Queue" = queue.Queue()
        self.stop_event = threading.Event()
        self.generating = False
        self.current_response = ""

        self._bubbles: list[dict] = []   # {"label", "frac"} for reflow
        self._stream_label = None
        self._stream_frac = 0.80
        self.placeholder = None

        self.side_row = None             # sidebar widgets (set by app)
        self.side_label = None

        self._build_page()

    # ---- page construction ----------------------------------------------------

    def _build_page(self):
        self.page = tk.Frame(self.app.content, bg=C["chat_bg"])

        # Scrolling transcript --------------------------------------------------
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

        # Composer --------------------------------------------------------------
        bar = tk.Frame(self.page, bg=C["chat_bg"])
        bar.pack(side="bottom", fill="x", padx=18, pady=(6, 16))

        box = tk.Frame(bar, bg=C["composer"], highlightthickness=1,
                       highlightbackground=C["composer_border"],
                       highlightcolor=C["accent"])
        box.pack(fill="x")

        # Pack the button first: a left-side widget with expand=True would
        # otherwise claim the whole row and leave the button unmapped.
        self.send_btn = tk.Label(box, text="Send", bg=C["accent"], fg="#ffffff",
                                 font=self.app.fonts["bold"], padx=18, pady=8, cursor="hand2")
        self.send_btn.pack(side="right", padx=8, pady=8)
        self.send_btn.bind("<Button-1>", lambda e: self._on_action())
        self._hover(self.send_btn, C["accent"], C["accent_hover"])

        self.input = tk.Text(box, height=1, bg=C["composer"], fg=C["text"],
                             wrap="word", relief="flat", bd=0, padx=14, pady=12,
                             insertbackground=C["text"], font=self.app.fonts["body"],
                             highlightthickness=0)
        self.input.pack(side="left", fill="both", expand=True)

        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", lambda e: None)  # allow newline
        self.input.bind("<KeyRelease>", self._autosize_input)

    # ---- placeholder / empty state -------------------------------------------

    def _show_placeholder(self):
        self.placeholder = tk.Frame(self.inner, bg=C["chat_bg"])
        self.placeholder.pack(fill="x", pady=(140, 0))
        tk.Label(self.placeholder, text="Ask anything", bg=C["chat_bg"], fg=C["text"],
                 font=self.app.fonts["title"]).pack()
        tk.Label(self.placeholder, text="Your messages stay on this machine, served locally by Ollama.",
                 bg=C["chat_bg"], fg=C["muted"], font=self.app.fonts["small"]).pack(pady=(6, 0))

    def _clear_placeholder(self):
        if self.placeholder is not None:
            self.placeholder.destroy()
            self.placeholder = None

    # ---- scrolling ------------------------------------------------------------

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._window, width=event.width)
        for b in self._bubbles:
            b["label"].configure(wraplength=max(220, int(event.width * b["frac"])))

    def _bind_wheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif abs(event.delta) >= 120:          # Windows
            delta = -int(event.delta / 120)
        else:                                   # macOS
            delta = -event.delta
        self.canvas.yview_scroll(delta, "units")

    def _near_bottom(self):
        try:
            return self.canvas.yview()[1] >= 0.999
        except tk.TclError:
            return True

    def _scroll_to_bottom(self):
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)

    # ---- bubbles --------------------------------------------------------------

    def _add_bubble(self, text, *, role):
        self._clear_placeholder()
        stick = self._near_bottom()

        user = role == "user"
        frac = 0.72 if user else 0.80
        bg = C["bubble_user"] if user else C["bubble_asst"]
        fg = C["bubble_user_fg"] if user else C["bubble_asst_fg"]

        row = tk.Frame(self.inner, bg=C["chat_bg"])
        row.pack(fill="x", padx=16, pady=(8, 0))

        col = tk.Frame(row, bg=C["chat_bg"])
        col.pack(side="right" if user else "left", anchor="e" if user else "w")

        caption = "You" if user else self.app.model_var.get() or "Assistant"
        tk.Label(col, text=caption, bg=C["chat_bg"], fg=C["faint"],
                 font=self.app.fonts["caption"]).pack(anchor="e" if user else "w",
                                                       padx=4, pady=(0, 2))

        wrap = max(220, int(self.canvas.winfo_width() * frac))
        label = tk.Label(col, text=text, bg=bg, fg=fg, justify="left", anchor="w",
                         wraplength=wrap, font=self.app.fonts["body"], padx=14, pady=10)
        label.pack(anchor="e" if user else "w")

        self._bubbles.append({"label": label, "frac": frac})
        if stick:
            self._scroll_to_bottom()
        return label

    # ---- sending / streaming --------------------------------------------------

    def _on_return(self, _event):
        self._on_action()
        return "break"

    def _on_action(self):
        if self.generating:
            self.stop()
        else:
            self.send()

    def send(self):
        if self.generating:
            return
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        model = self.app.model_var.get().strip()
        if not model:
            self.app.set_status("No model selected — pull one with 'ollama pull <name>', then ↻")
            return

        self.input.delete("1.0", "end")
        self._autosize_input()
        self._add_bubble(text, role="user")
        self.messages.append({"role": "user", "content": text})
        if len(self.messages) == 1:
            self.set_title(text)

        self.generating = True
        self.stop_event.clear()
        self.current_response = ""
        self._set_busy(True)
        self.app.set_status(f"{model} is thinking…")
        self._stream_label = self._add_bubble("…", role="assistant")

        snapshot = list(self.messages)
        threading.Thread(target=self._worker, args=(model, snapshot), daemon=True).start()

    def _worker(self, model, messages):
        try:
            for chunk in backend.chat_stream(model, messages, self.stop_event.is_set):
                self.queue.put(("chunk", chunk))
        except backend.OllamaError as exc:
            self.queue.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive
            self.queue.put(("error", f"Unexpected error: {exc}"))
        finally:
            self.queue.put(("done", None))

    def drain(self):
        """Apply pending worker output on the main thread."""
        if not self.generating:
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "chunk":
                    self.current_response += payload
                    stick = self._near_bottom()
                    self._stream_label.configure(text=self.current_response)
                    if stick:
                        self._scroll_to_bottom()
                elif kind == "error":
                    self.current_response = ""
                    if self._stream_label is not None:
                        self._stream_label.configure(
                            text="⚠ " + payload, bg="#2a1b1d", fg=C["danger"])
                    self.app.set_status("Error")
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass

    def _finish(self):
        if self.current_response.strip():
            self.messages.append({"role": "assistant", "content": self.current_response})
        elif self._stream_label is not None and self._stream_label["text"] == "…":
            self._stream_label.configure(text="(no response)", fg=C["muted"])
        self._stream_label = None
        self.generating = False
        self._set_busy(False)
        self.app.set_status("Ready")

    def stop(self):
        if self.generating:
            self.stop_event.set()
            self.app.set_status("Stopping…")

    def clear(self):
        if self.generating:
            self.stop()
        self.messages.clear()
        self._bubbles.clear()
        for child in self.inner.winfo_children():
            child.destroy()
        self.placeholder = None
        self._show_placeholder()

    def set_title(self, text):
        clean = " ".join(text.split())
        self.title = (clean[:30] + "…") if len(clean) > 31 else clean or "New chat"
        if self.side_label is not None:
            self.side_label.configure(text=self.title)
        if self.app.active is self:
            self.app.header_title.configure(text=self.title)

    # ---- widget state ---------------------------------------------------------

    def _set_busy(self, busy):
        if busy:
            self.send_btn.configure(text="Stop", bg=C["danger"])
            self._hover(self.send_btn, C["danger"], C["danger_hover"])
        else:
            self.send_btn.configure(text="Send", bg=C["accent"])
            self._hover(self.send_btn, C["accent"], C["accent_hover"])
            self.input.focus_set()

    def _autosize_input(self, _event=None):
        lines = int(self.input.index("end-1c").split(".")[0])
        self.input.configure(height=max(1, min(lines, 6)))

    def _hover(self, widget, base, hover):
        widget.bind("<Enter>", lambda e: widget.configure(bg=hover))
        widget.bind("<Leave>", lambda e: widget.configure(bg=base))


class ChatApp:
    """Top-level window: sidebar, header, conversation pages, and the poll loop."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Local LLM Chat")
        self.root.geometry("960x680")
        self.root.minsize(720, 480)
        self.root.configure(bg=C["app_bg"])

        ui = _pick_family(root, "SF Pro Text", "Segoe UI", "Helvetica Neue", "Helvetica", "Arial")
        self.fonts = {
            "title": tkfont.Font(family=ui, size=20, weight="bold"),
            "header": tkfont.Font(family=ui, size=14, weight="bold"),
            "bold": tkfont.Font(family=ui, size=12, weight="bold"),
            "body": tkfont.Font(family=ui, size=13),
            "small": tkfont.Font(family=ui, size=11),
            "caption": tkfont.Font(family=ui, size=10),
        }

        self.model_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.conversations: list[Conversation] = []
        self.active: Conversation | None = None

        self._setup_styles()
        self._build_ui()
        self.refresh_models()
        self.new_conversation()
        self.root.after(POLL_MS, self._poll)

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
        style.configure("Model.TCombobox", fieldbackground=C["sidebar_active"],
                        background=C["sidebar_active"], foreground=C["text"],
                        arrowcolor=C["text"], bordercolor=C["border"],
                        lightcolor=C["border"], darkcolor=C["border"], padding=5)
        # readonly is its own ttk state — without these maps the field renders
        # as a white box with a highlighted selection.
        style.map("Model.TCombobox",
                  fieldbackground=[("readonly", C["sidebar_active"]), ("disabled", C["header"])],
                  foreground=[("readonly", C["text"]), ("disabled", C["faint"])],
                  background=[("readonly", C["sidebar_active"])],
                  arrowcolor=[("readonly", C["text"]), ("disabled", C["faint"])],
                  selectbackground=[("readonly", C["sidebar_active"])],
                  selectforeground=[("readonly", C["text"])])
        self.root.option_add("*TCombobox*Listbox.background", C["sidebar_active"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.root.option_add("*TCombobox*Listbox.font", self.fonts["body"])

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=C["app_bg"])
        outer.pack(fill="both", expand=True)

        # ---- sidebar ----
        sidebar = tk.Frame(outer, bg=C["sidebar"], width=230)
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
        new_btn.bind("<Enter>", lambda e: new_btn.configure(bg=C["sidebar_hover"]))
        new_btn.bind("<Leave>", lambda e: new_btn.configure(bg=C["sidebar_active"]))

        self.side_list = tk.Frame(sidebar, bg=C["sidebar"])
        self.side_list.pack(fill="both", expand=True, padx=8)

        # ---- main area ----
        main = tk.Frame(outer, bg=C["app_bg"])
        main.pack(side="left", fill="both", expand=True)

        header = tk.Frame(main, bg=C["header"], height=58)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        self.header_title = tk.Label(header, text="New chat", bg=C["header"], fg=C["text"],
                                     font=self.fonts["header"])
        self.header_title.pack(side="left", padx=20)

        refresh = tk.Label(header, text="↻", bg=C["header"], fg=C["muted"],
                           font=self.fonts["header"], cursor="hand2")
        refresh.pack(side="right", padx=(6, 16))
        refresh.bind("<Button-1>", lambda e: self.refresh_models())
        refresh.bind("<Enter>", lambda e: refresh.configure(fg=C["text"]))
        refresh.bind("<Leave>", lambda e: refresh.configure(fg=C["muted"]))

        self.model_combo = ttk.Combobox(header, textvariable=self.model_var, width=20,
                                        state="readonly", style="Model.TCombobox",
                                        font=self.fonts["body"])
        self.model_combo.pack(side="right", pady=12)
        tk.Label(header, text="Model", bg=C["header"], fg=C["muted"],
                 font=self.fonts["small"]).pack(side="right", padx=(0, 8))

        self.content = tk.Frame(main, bg=C["chat_bg"])
        self.content.pack(side="top", fill="both", expand=True)

        status = tk.Frame(main, bg=C["header"], height=26)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        tk.Label(status, textvariable=self.status_var, bg=C["header"], fg=C["muted"],
                 font=self.fonts["small"]).pack(side="left", padx=20)

    # ---- conversation management ----------------------------------------------

    def new_conversation(self):
        conv = Conversation(self)
        self.conversations.append(conv)
        self._add_sidebar_row(conv)
        self.show(conv)

    def _add_sidebar_row(self, conv):
        row = tk.Frame(self.side_list, bg=C["sidebar"])
        row.pack(fill="x", pady=2)
        label = tk.Label(row, text=conv.title, bg=C["sidebar"], fg=C["muted"],
                         font=self.fonts["body"], anchor="w", padx=10, pady=8, cursor="hand2")
        label.pack(side="left", fill="x", expand=True)
        delete = tk.Label(row, text="✕", bg=C["sidebar"], fg=C["faint"],
                          font=self.fonts["small"], padx=8, cursor="hand2")
        delete.pack(side="right")

        conv.side_row = row
        conv.side_label = label
        label.bind("<Button-1>", lambda e: self.show(conv))
        row.bind("<Button-1>", lambda e: self.show(conv))
        delete.bind("<Button-1>", lambda e: self.delete_conversation(conv))
        delete.bind("<Enter>", lambda e: delete.configure(fg=C["danger"]))
        delete.bind("<Leave>", lambda e: delete.configure(fg=C["faint"]))
        self._style_sidebar()

    def show(self, conv):
        if self.active is conv:
            self._style_sidebar()
            return
        if self.active is not None:
            self.active.page.pack_forget()
        self.active = conv
        conv.page.pack(fill="both", expand=True)
        self.header_title.configure(text=conv.title)
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

    def _style_sidebar(self):
        for conv in self.conversations:
            active = conv is self.active
            bg = C["sidebar_active"] if active else C["sidebar"]
            conv.side_row.configure(bg=bg)
            conv.side_label.configure(bg=bg, fg=C["text"] if active else C["muted"])
            for child in conv.side_row.winfo_children():
                if child is not conv.side_label:
                    child.configure(bg=bg)

    # ---- models ---------------------------------------------------------------

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
                self.set_status("No models installed — pull one: ollama pull llama3.1:8b, then ↻")
            else:
                self.set_status("Ollama not reachable — start it with 'ollama serve', then ↻")

    def set_status(self, text):
        self.status_var.set(text)

    def _poll(self):
        for conv in self.conversations:
            conv.drain()
        self.root.after(POLL_MS, self._poll)


def main():
    root = tk.Tk()
    ChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
