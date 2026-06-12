"""A small desktop chat client for local LLMs served by Ollama.

The app keeps the Tkinter event loop responsive by running every model call on
a background thread and streaming the reply back to the UI through a queue, so
the window never freezes while a model is thinking. Each tab is an independent
conversation with its own history, so the model actually remembers the thread.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.font import Font

import requestLocal as backend

POLL_MS = 40  # how often the UI drains worker output

PALETTE = {
    "bg": "#1e1e1e",
    "panel": "#252526",
    "input_bg": "#2d2d30",
    "fg": "#e6e6e6",
    "muted": "#9aa0a6",
    "user": "#4ec9b0",
    "assistant": "#dcdcdc",
    "accent": "#0a84ff",
    "error": "#f48771",
    "border": "#3c3c3c",
}


class ChatTab:
    """One conversation: a transcript, an input box, and its own history."""

    def __init__(self, app: "ChatApp", frame, chat_log, entry, send_btn, stop_btn):
        self.app = app
        self.frame = frame
        self.chat_log = chat_log
        self.entry = entry
        self.send_btn = send_btn
        self.stop_btn = stop_btn

        self.messages: list[dict] = []
        self.queue: "queue.Queue" = queue.Queue()
        self.stop_event = threading.Event()
        self.generating = False
        self.current_response = ""

        self._configure_tags()
        self._system(
            "New conversation. Type a message and press Enter to send "
            "(Shift+Enter for a new line)."
        )

    # ---- transcript rendering -------------------------------------------------

    def _configure_tags(self):
        self.chat_log.tag_configure(
            "user_label", foreground=PALETTE["user"], font=self.app.fonts["bold"],
            spacing1=10, spacing3=2,
        )
        self.chat_log.tag_configure(
            "asst_label", foreground=PALETTE["accent"], font=self.app.fonts["bold"],
            spacing1=10, spacing3=2,
        )
        self.chat_log.tag_configure("user_text", foreground=PALETTE["fg"], lmargin1=8, lmargin2=8)
        self.chat_log.tag_configure("asst_text", foreground=PALETTE["assistant"], lmargin1=8, lmargin2=8)
        self.chat_log.tag_configure("error", foreground=PALETTE["error"], lmargin1=8, lmargin2=8, spacing1=6)
        self.chat_log.tag_configure(
            "system", foreground=PALETTE["muted"], font=self.app.fonts["italic"], spacing1=4,
        )

    def _write(self, text, tag):
        self.chat_log.config(state="normal")
        self.chat_log.insert("end", text, tag)
        self.chat_log.see("end")
        self.chat_log.config(state="disabled")

    def _system(self, text):
        self._write(text + "\n", "system")

    def _append_user(self, text):
        self._write("You\n", "user_label")
        self._write(text + "\n", "user_text")

    def _begin_assistant(self):
        self._write("Assistant\n", "asst_label")

    def _append_assistant_chunk(self, chunk):
        self._write(chunk, "asst_text")

    def _end_assistant(self):
        self._write("\n", "asst_text")

    def _append_error(self, message):
        self._write("⚠ " + message + "\n", "error")

    # ---- sending / streaming --------------------------------------------------

    def send(self, _event=None):
        if self.generating:
            return "break"
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return "break"
        self.entry.delete("1.0", "end")
        self._append_user(text)
        self.messages.append({"role": "user", "content": text})
        self._start_generation()
        return "break"

    def _start_generation(self):
        model = self.app.model_var.get().strip()
        if not model:
            self._append_error("Pick a model first.")
            return
        self.generating = True
        self.stop_event.clear()
        self.current_response = ""
        self._set_busy(True)
        self.app.set_status(f"{model} is thinking…")
        self._begin_assistant()
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
        """Pull any pending worker output onto the transcript (main thread)."""
        if not self.generating:
            return
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "chunk":
                    self.current_response += payload
                    self._append_assistant_chunk(payload)
                elif kind == "error":
                    self._append_error(payload)
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass

    def _finish(self):
        if self.current_response.strip():
            self.messages.append({"role": "assistant", "content": self.current_response})
        else:
            self._system("(no response)")
        self._end_assistant()
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
        self.chat_log.config(state="normal")
        self.chat_log.delete("1.0", "end")
        self.chat_log.config(state="disabled")
        self._system("Conversation cleared.")

    def _set_busy(self, busy):
        self.send_btn.config(state="disabled" if busy else "normal")
        self.stop_btn.config(state="normal" if busy else "disabled")
        self.entry.config(state="disabled" if busy else "normal")
        if not busy:
            self.entry.focus_set()


class ChatApp:
    """Top-level window: model picker, tabs, and the UI poll loop."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Local LLM Chat")
        self.root.geometry("860x660")
        self.root.minsize(620, 460)
        self.root.configure(bg=PALETTE["bg"])

        self.fonts = {
            "main": Font(family="Helvetica", size=12),
            "bold": Font(family="Helvetica", size=12, weight="bold"),
            "italic": Font(family="Helvetica", size=11, slant="italic"),
            "chat": Font(family="Helvetica", size=13),
        }

        self.model_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.tabs: list[ChatTab] = []
        self.tab_by_id: dict[str, ChatTab] = {}

        self._setup_styles()
        self._build_ui()
        self.refresh_models()
        self.add_tab()
        self.root.after(POLL_MS, self._poll)

    def _setup_styles(self):
        style = ttk.Style()
        # 'clam' actually honours custom colours on every platform (the native
        # macOS/Windows themes largely ignore them).
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=PALETTE["bg"])
        style.configure("Panel.TFrame", background=PALETTE["panel"])
        style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["fg"], font=self.fonts["main"])
        style.configure("Panel.TLabel", background=PALETTE["panel"], foreground=PALETTE["fg"], font=self.fonts["main"])
        style.configure("Status.TLabel", background=PALETTE["panel"], foreground=PALETTE["muted"], font=self.fonts["italic"])
        style.configure(
            "TButton", background=PALETTE["input_bg"], foreground=PALETTE["fg"],
            font=self.fonts["main"], padding=6, borderwidth=0,
        )
        style.map(
            "TButton",
            background=[("active", PALETTE["border"]), ("disabled", PALETTE["panel"])],
            foreground=[("disabled", PALETTE["muted"])],
        )
        style.configure(
            "Accent.TButton", background=PALETTE["accent"], foreground="#ffffff",
            font=self.fonts["bold"], padding=6, borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", "#0066cc"), ("disabled", PALETTE["panel"])])
        style.configure(
            "TCombobox", fieldbackground=PALETTE["input_bg"], background=PALETTE["input_bg"],
            foreground=PALETTE["fg"], arrowcolor=PALETTE["fg"], padding=4,
        )
        style.configure(
            "TNotebook", background=PALETTE["bg"], borderwidth=0, tabmargins=[2, 4, 2, 0],
        )
        style.configure(
            "TNotebook.Tab", background=PALETTE["panel"], foreground=PALETTE["muted"],
            padding=[12, 6], font=self.fonts["main"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", PALETTE["bg"])],
            foreground=[("selected", PALETTE["fg"])],
        )

    def _build_ui(self):
        container = ttk.Frame(self.root, style="TFrame")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- top control panel ----
        panel = ttk.Frame(container, style="Panel.TFrame")
        panel.pack(fill="x", pady=(0, 8))

        ttk.Label(panel, text="Model:", style="Panel.TLabel").pack(side="left", padx=(8, 4), pady=8)
        self.model_combo = ttk.Combobox(panel, textvariable=self.model_var, width=22, style="TCombobox")
        self.model_combo.pack(side="left", padx=4, pady=8)
        ttk.Button(panel, text="↻ Refresh", command=self.refresh_models).pack(side="left", padx=4, pady=8)

        ttk.Label(panel, textvariable=self.status_var, style="Status.TLabel").pack(side="right", padx=10)

        ttk.Button(panel, text="New Chat", command=self.add_tab).pack(side="left", padx=4, pady=8)
        ttk.Button(panel, text="Clear", command=self._clear_current).pack(side="left", padx=4, pady=8)
        ttk.Button(panel, text="Delete Chat", command=self.delete_tab).pack(side="left", padx=4, pady=8)

        # ---- tabs ----
        self.notebook = ttk.Notebook(container, style="TNotebook")
        self.notebook.pack(fill="both", expand=True)

    def add_tab(self):
        frame = ttk.Frame(self.notebook, style="TFrame")

        chat_log = tk.Text(
            frame, font=self.fonts["chat"], bg=PALETTE["input_bg"], fg=PALETTE["fg"],
            wrap="word", state="disabled", relief="flat", padx=12, pady=10,
            insertbackground=PALETTE["fg"], highlightthickness=0, borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(frame, command=chat_log.yview)
        chat_log.configure(yscrollcommand=scrollbar.set)
        chat_log.pack(side="top", fill="both", expand=True, pady=(6, 6))
        scrollbar.place(in_=chat_log, relx=1.0, rely=0, relheight=1.0, anchor="ne")

        input_row = ttk.Frame(frame, style="TFrame")
        input_row.pack(side="bottom", fill="x")

        entry = tk.Text(
            input_row, font=self.fonts["main"], height=3, bg=PALETTE["input_bg"], fg=PALETTE["fg"],
            wrap="word", relief="flat", padx=8, pady=6,
            insertbackground=PALETTE["fg"], highlightthickness=1,
            highlightbackground=PALETTE["border"], highlightcolor=PALETTE["accent"],
        )
        entry.pack(side="left", fill="both", expand=True, padx=(0, 8))

        button_col = ttk.Frame(input_row, style="TFrame")
        button_col.pack(side="right", fill="y")
        send_btn = ttk.Button(button_col, text="Send", style="Accent.TButton")
        send_btn.pack(side="top", fill="x", pady=(0, 4))
        stop_btn = ttk.Button(button_col, text="Stop", state="disabled")
        stop_btn.pack(side="top", fill="x")

        tab = ChatTab(self, frame, chat_log, entry, send_btn, stop_btn)
        send_btn.config(command=tab.send)
        stop_btn.config(command=tab.stop)
        entry.bind("<Return>", tab.send)
        entry.bind("<Shift-Return>", lambda e: (entry.insert("insert", "\n"), "break")[1])

        self.tabs.append(tab)
        self.tab_by_id[str(frame)] = tab
        self.notebook.add(frame, text=f"Chat {len(self.tabs)}")
        self.notebook.select(frame)
        entry.focus_set()

    def current_tab(self) -> ChatTab | None:
        selected = self.notebook.select()
        return self.tab_by_id.get(selected)

    def delete_tab(self):
        if len(self.tabs) <= 1:
            self.set_status("Can't delete the last chat.")
            return
        tab = self.current_tab()
        if tab is None:
            return
        tab.stop()
        self.notebook.forget(tab.frame)
        self.tabs.remove(tab)
        self.tab_by_id.pop(str(tab.frame), None)
        self._renumber_tabs()

    def _renumber_tabs(self):
        for index, tab in enumerate(self.tabs, start=1):
            self.notebook.tab(tab.frame, text=f"Chat {index}")

    def _clear_current(self):
        tab = self.current_tab()
        if tab is not None:
            tab.clear()

    def refresh_models(self):
        models = backend.list_models()
        if models:
            self.model_combo["values"] = models
            if self.model_var.get() not in models:
                self.model_var.set(models[0])
            self.set_status(f"{len(models)} model(s) available")
        else:
            self.model_combo["values"] = backend.DEFAULT_MODELS
            if not self.model_var.get():
                self.model_var.set(backend.DEFAULT_MODELS[0])
            self.set_status("Ollama not reachable — run 'ollama serve', then Refresh")

    def set_status(self, text):
        self.status_var.set(text)

    def _poll(self):
        for tab in self.tabs:
            tab.drain()
        self.root.after(POLL_MS, self._poll)


def main():
    root = tk.Tk()
    ChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
