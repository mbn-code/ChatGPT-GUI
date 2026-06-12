"""A desktop chat client for local LLMs served by Ollama.

A modern Qt (PySide6) interface: a sidebar of saved conversations, a scrolling
transcript of rounded message bubbles with Markdown and syntax-highlighted code,
and a composer at the bottom. Model calls run on a background thread and stream
their reply back via Qt signals, so the window never freezes. Conversations and
settings persist to disk.
"""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QScrollArea, QSlider,
    QStackedWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

import mdrender
import requestLocal as backend
import storage

PALETTE = {
    "app_bg": "#0e1016",
    "sidebar": "#14171f",
    "sidebar_active": "#222838",
    "sidebar_hover": "#1b1f2b",
    "header": "#14171f",
    "chat_bg": "#0e1016",
    "composer": "#1a1e29",
    "border": "#262c3b",
    "bubble_user": "#3b6ef5",
    "bubble_user_fg": "#ffffff",
    "bubble_asst": "#1c212e",
    "bubble_asst_fg": "#e8eaf0",
    "text": "#e8eaf0",
    "muted": "#8b91a3",
    "faint": "#5c6376",
    "accent": "#3b6ef5",
    "accent_hover": "#4f7df7",
    "danger": "#e2554e",
    "code_bg": "#0a0c12",
    "code_header": "#11141d",
    "code_inline_bg": "#2a3042",
    "code_inline_fg": "#e6b673",
    "link": "#6ea8ff",
    "field": "#222838",
}

STYLE = """
* { color: %(text)s; font-size: 14px; }
QMainWindow, QWidget { background: %(app_bg)s; }
QToolTip { background: %(sidebar_active)s; color: %(text)s; border: 1px solid %(border)s; }

#sidebar { background: %(sidebar)s; border: none; }
#brand { font-size: 16px; font-weight: 600; }
#newChat {
    background: %(sidebar_active)s; border: none; border-radius: 10px;
    padding: 11px 14px; text-align: left; font-weight: 600;
}
#newChat:hover { background: %(sidebar_hover)s; }
#chatItem {
    background: transparent; border: none; border-radius: 8px;
    padding: 9px 10px; text-align: left; color: %(muted)s;
}
#chatItem:hover { background: %(sidebar_hover)s; }
#chatItem:checked { background: %(sidebar_active)s; color: %(text)s; }
#chatDelete { background: transparent; border: none; color: %(faint)s; padding: 2px 6px; }
#chatDelete:hover { color: %(danger)s; }
#footerBtn {
    background: transparent; border: none; border-radius: 8px;
    padding: 9px 10px; text-align: left; color: %(muted)s;
}
#footerBtn:hover { background: %(sidebar_hover)s; color: %(text)s; }

#header { background: %(header)s; border-bottom: 1px solid %(border)s; }
#title { font-size: 16px; font-weight: 600; }
#headerBtn { background: transparent; border: none; color: %(muted)s; padding: 6px 10px; border-radius: 8px; }
#headerBtn:hover { background: %(sidebar_hover)s; color: %(text)s; }
#caption { color: %(faint)s; font-size: 11px; }

QComboBox#modelCombo {
    background: %(field)s; border: 1px solid %(border)s; border-radius: 8px;
    padding: 5px 10px; min-width: 150px; color: %(text)s;
}
QComboBox#modelCombo:hover { border-color: %(accent)s; }
QComboBox#modelCombo::drop-down { border: none; width: 22px; }
QComboBox#modelCombo QAbstractItemView {
    background: %(field)s; color: %(text)s; border: 1px solid %(border)s;
    selection-background-color: %(accent)s; outline: none;
}

#userBubble { background: %(bubble_user)s; border-radius: 14px; }
#userBubble QLabel { color: %(bubble_user_fg)s; background: transparent; }
#asstBubble { background: %(bubble_asst)s; border-radius: 14px; }
#asstBubble QLabel { color: %(bubble_asst_fg)s; background: transparent; }
#bubbleText { padding: 11px 14px; }

#codeBlock { background: %(code_bg)s; border-radius: 10px; border: 1px solid %(border)s; }
#codeHeader { background: %(code_header)s; border-top-left-radius: 10px; border-top-right-radius: 10px; }
#codeLang { color: %(muted)s; font-size: 11px; }
#codeText { background: %(code_bg)s; padding: 10px 12px;
            font-family: 'SF Mono','Menlo','Consolas',monospace; font-size: 13px; }
#copyCode { background: transparent; border: none; color: %(muted)s; font-size: 11px; padding: 4px 8px; }
#copyCode:hover { color: %(text)s; }
#linkBtn { background: transparent; border: none; color: %(faint)s; font-size: 12px; padding: 2px 8px; }
#linkBtn:hover { color: %(text)s; }

#composerWrap { background: %(chat_bg)s; }
#composer { background: %(composer)s; border: 1px solid %(border)s; border-radius: 14px; }
#composer:focus-within { border-color: %(accent)s; }
QTextEdit#composerInput {
    background: transparent; border: none; padding: 10px 12px; color: %(text)s;
    selection-background-color: %(accent)s;
}
#sendBtn {
    background: %(accent)s; color: #ffffff; border: none; border-radius: 10px;
    padding: 9px 18px; font-weight: 600;
}
#sendBtn:hover { background: %(accent_hover)s; }
#sendBtn[stopping="true"] { background: %(danger)s; }

QScrollArea, #chatScroll { background: %(chat_bg)s; border: none; }
#chatInner { background: %(chat_bg)s; }
#placeholderTitle { font-size: 22px; font-weight: 600; }
#placeholderSub { color: %(muted)s; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(faint)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QStatusBar { background: %(header)s; color: %(muted)s; border-top: 1px solid %(border)s; }
QStatusBar::item { border: none; }

QDialog { background: %(app_bg)s; }
QDialog QLabel { color: %(text)s; }
#dialogTitle { font-size: 18px; font-weight: 600; }
#dialogHint { color: %(muted)s; font-size: 12px; }
QLineEdit, QDialog QTextEdit {
    background: %(field)s; border: 1px solid %(border)s; border-radius: 8px;
    padding: 8px 10px; color: %(text)s; selection-background-color: %(accent)s;
}
QLineEdit:focus, QDialog QTextEdit:focus { border-color: %(accent)s; }
QComboBox {
    background: %(field)s; border: 1px solid %(border)s; border-radius: 8px;
    padding: 6px 10px; color: %(text)s;
}
QComboBox QAbstractItemView {
    background: %(field)s; color: %(text)s; selection-background-color: %(accent)s;
}
#primaryBtn { background: %(accent)s; color: #fff; border: none; border-radius: 9px; padding: 8px 18px; font-weight: 600; }
#primaryBtn:hover { background: %(accent_hover)s; }
#ghostBtn { background: %(field)s; color: %(text)s; border: none; border-radius: 9px; padding: 8px 16px; }
#ghostBtn:hover { background: %(sidebar_hover)s; }
#modelRow { background: %(sidebar)s; border-radius: 10px; }
#deleteBtn { background: transparent; border: none; color: %(faint)s; padding: 4px 10px; }
#deleteBtn:hover { color: %(danger)s; }
QProgressBar {
    background: %(field)s; border: none; border-radius: 6px; height: 10px; text-align: center;
}
QProgressBar::chunk { background: %(accent)s; border-radius: 6px; }
QSlider::groove:horizontal { height: 5px; background: %(field)s; border-radius: 3px; }
QSlider::handle:horizontal { background: %(accent)s; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 3px; }
""" % PALETTE


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class CodeBlock(QFrame):
    """A syntax-highlighted code block with a language label and Copy button."""

    def __init__(self, app, code, lang):
        super().__init__()
        self.setObjectName("codeBlock")
        self._code = code
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        header = QFrame()
        header.setObjectName("codeHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 4, 6, 4)
        lang_label = QLabel(lang or "code")
        lang_label.setObjectName("codeLang")
        h.addWidget(lang_label)
        h.addStretch()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("copyCode")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        h.addWidget(self.copy_btn)
        v.addWidget(header)

        body = QLabel()
        body.setObjectName("codeText")
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setText(f"<pre style='margin:0;white-space:pre-wrap;'>"
                     f"{mdrender.highlight_to_html(code, lang)}</pre>")
        v.addWidget(body)
        self._app = app

    def _copy(self):
        QGuiApplication.clipboard().setText(self._code)
        self.copy_btn.setText("Copied")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copy"))


class MessageBubble(QWidget):
    """One message: a role caption, a rounded bubble, and (assistant) actions."""

    def __init__(self, app, role, model_name=""):
        super().__init__()
        self.app = app
        self.role = role
        user = role == "user"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)

        cap_row = QHBoxLayout()
        caption = QLabel("You" if user else (model_name or "Assistant"))
        caption.setObjectName("caption")
        if user:
            cap_row.addStretch()
            cap_row.addWidget(caption)
        else:
            cap_row.addWidget(caption)
            cap_row.addStretch()
        outer.addLayout(cap_row)

        bubble_row = QHBoxLayout()
        self.frame = QFrame()
        self.frame.setObjectName("userBubble" if user else "asstBubble")
        self.frame.setMaximumWidth(720)
        self.content = QVBoxLayout(self.frame)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(8)
        if user:
            bubble_row.addStretch()
            bubble_row.addWidget(self.frame)
        else:
            bubble_row.addWidget(self.frame)
            bubble_row.addStretch()
        outer.addLayout(bubble_row)

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(2, 0, 0, 0)
        outer.addLayout(self.actions)
        self._stream_label = None

    def set_max_width(self, width):
        self.frame.setMaximumWidth(max(320, width))

    def set_plain(self, text):
        if self._stream_label is None:
            clear_layout(self.content)
            self._stream_label = QLabel()
            self._stream_label.setObjectName("bubbleText")
            self._stream_label.setWordWrap(True)
            self._stream_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.content.addWidget(self._stream_label)
        self._stream_label.setText(text or "…")

    def render(self, text):
        self._stream_label = None
        clear_layout(self.content)
        segments = mdrender.parse_segments(text)
        if not segments:
            segments = [{"type": "prose", "text": text}]
        for seg in segments:
            if seg["type"] == "code":
                self.content.addWidget(CodeBlock(self.app, seg["code"], seg["lang"]))
            else:
                lbl = QLabel(mdrender.prose_to_html(seg["text"], PALETTE))
                lbl.setObjectName("bubbleText")
                lbl.setTextFormat(Qt.RichText)
                lbl.setWordWrap(True)
                lbl.setOpenExternalLinks(True)
                lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
                self.content.addWidget(lbl)

    def set_error(self, message):
        self._stream_label = None
        clear_layout(self.content)
        lbl = QLabel("⚠ " + message)
        lbl.setObjectName("bubbleText")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{PALETTE['danger']};")
        self.content.addWidget(lbl)

    def add_action(self, text, callback):
        btn = QPushButton(text)
        btn.setObjectName("linkBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        self.actions.addWidget(btn, alignment=Qt.AlignLeft)
        return btn

    def clear_actions(self):
        clear_layout(self.actions)


class Conversation(QObject):
    """One chat thread: history, its page widget, and streaming via signals."""

    chunk = Signal(str)
    failed = Signal(str)
    finished = Signal(dict)

    def __init__(self, app, *, title="New chat", system="", model="", messages=None):
        super().__init__()
        self.app = app
        self.title = title or "New chat"
        self.system = system
        self.model = model
        self.messages = []

        self.generating = False
        self.stop_event = threading.Event()
        self._response = ""
        self._meta = {}
        self._bubbles = []
        self._stream_bubble = None

        self.chunk.connect(self._on_chunk)
        self.failed.connect(self._on_failed)
        self.finished.connect(self._on_finished)

        self._build_page()
        for m in (messages or []):
            self._add_bubble(m["role"], m["content"])
            self.messages.append({"role": m["role"], "content": m["content"]})
        if self.messages:
            self._clear_placeholder()
            self._refresh_actions()

    # ---- page -----------------------------------------------------------------

    def _build_page(self):
        self.page = QWidget()
        v = QVBoxLayout(self.page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("chatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setFocusPolicy(Qt.NoFocus)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner.setObjectName("chatInner")
        self.col = QVBoxLayout(self.inner)
        self.col.setContentsMargins(26, 18, 26, 18)
        self.col.setSpacing(6)
        self.col.addStretch()
        self.scroll.setWidget(self.inner)
        v.addWidget(self.scroll, 1)

        self._placeholder = self._make_placeholder()
        self.col.insertWidget(0, self._placeholder)

        wrap = QFrame()
        wrap.setObjectName("composerWrap")
        wv = QHBoxLayout(wrap)
        wv.setContentsMargins(26, 8, 26, 18)
        composer = QFrame()
        composer.setObjectName("composer")
        cv = QHBoxLayout(composer)
        cv.setContentsMargins(6, 4, 6, 4)
        cv.setSpacing(6)
        self.input = QTextEdit()
        self.input.setObjectName("composerInput")
        self.input.setPlaceholderText("Message…  (Enter to send, Shift+Enter for newline)")
        self.input.setAcceptRichText(False)
        self.input.setFixedHeight(44)
        self.input.textChanged.connect(self._autosize_input)
        self.input.installEventFilter(self)
        cv.addWidget(self.input, 1)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_action)
        cv.addWidget(self.send_btn, alignment=Qt.AlignBottom)
        wv.addWidget(composer)
        v.addWidget(wrap)

        self.scroll.viewport().installEventFilter(self)

    def _make_placeholder(self):
        ph = QWidget()
        lay = QVBoxLayout(ph)
        lay.setContentsMargins(0, 120, 0, 0)
        t = QLabel("Ask anything")
        t.setObjectName("placeholderTitle")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("Your conversation stays on this machine, served locally by Ollama.")
        s.setObjectName("placeholderSub")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(s)
        return ph

    def _clear_placeholder(self):
        if self._placeholder is not None:
            self._placeholder.setParent(None)
            self._placeholder.deleteLater()
            self._placeholder = None

    def eventFilter(self, obj, event):
        try:
            etype = event.type()
            if etype == QEvent.KeyPress and obj is self.input:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
                        event.modifiers() & Qt.ShiftModifier):
                    self._on_action()
                    return True
            elif etype == QEvent.Resize and obj is self.scroll.viewport():
                self._relayout_widths()
        except RuntimeError:
            return False  # underlying C++ object gone (teardown)
        return super().eventFilter(obj, event)

    def _relayout_widths(self):
        width = max(360, int(self.scroll.viewport().width() * 0.82))
        for b in self._bubbles:
            b.set_max_width(width)

    def _autosize_input(self):
        doc_h = int(self.input.document().size().height())
        self.input.setFixedHeight(max(44, min(doc_h + 16, 150)))

    # ---- bubbles --------------------------------------------------------------

    def _add_bubble(self, role, content):
        self._clear_placeholder()
        bubble = MessageBubble(self.app, role, model_name=self.model or self.app.current_model())
        bubble.set_max_width(max(360, int(self.scroll.viewport().width() * 0.82)))
        if role == "user":
            bubble.set_plain(content)
        else:
            if content:
                bubble.render(content)
            else:
                bubble.set_plain("…")
        self.col.insertWidget(self.col.count() - 1, bubble)
        self._bubbles.append(bubble)
        return bubble

    def _scroll_to_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _at_bottom(self):
        bar = self.scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    # ---- send / stream --------------------------------------------------------

    def _on_action(self):
        self.stop() if self.generating else self.send()

    def send(self):
        if self.generating:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        if not self.app.current_model():
            self.app.set_status("No model selected — open Manage models to pull one")
            return
        self.input.clear()
        self._add_bubble("user", text)
        self.messages.append({"role": "user", "content": text})
        if len([m for m in self.messages if m["role"] == "user"]) == 1:
            self.set_title(text)
        self._scroll_to_bottom()
        self._start_stream()
        self.app.schedule_save()

    def regenerate(self):
        if self.generating or not self.messages or self.messages[-1]["role"] != "assistant":
            return
        self.messages.pop()
        for b in reversed(self._bubbles):
            if b.role == "assistant":
                self._bubbles.remove(b)
                b.setParent(None)
                b.deleteLater()
                break
        self._start_stream()

    def _start_stream(self):
        model = self.app.current_model()
        self.model = model
        self.generating = True
        self.stop_event.clear()
        self._response = ""
        self._meta = {}
        self.send_btn.setText("Stop")
        self.send_btn.setProperty("stopping", "true")
        self.send_btn.style().polish(self.send_btn)
        self.app.set_status(f"{model} is thinking…")
        self._stream_bubble = self._add_bubble("assistant", "")
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
            for piece in backend.chat_stream(model, messages, self.stop_event.is_set,
                                             options=options, meta=self._meta):
                self.chunk.emit(piece)
        except backend.OllamaError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover
            self.failed.emit(f"Unexpected error: {exc}")
        finally:
            self.finished.emit(self._meta)

    def _on_chunk(self, piece):
        stick = self._at_bottom()
        self._response += piece
        if self._stream_bubble is not None:
            self._stream_bubble.set_plain(self._response)
        if stick:
            self._scroll_to_bottom()

    def _on_failed(self, message):
        self._response = ""
        if self._stream_bubble is not None:
            self._stream_bubble.set_error(message)
        self.app.set_status("Error")

    def _on_finished(self, meta):
        text = self._response
        if text.strip() and self._stream_bubble is not None:
            self._stream_bubble.render(text)
            self.messages.append({"role": "assistant", "content": text})
        elif self._stream_bubble is not None and not text.strip():
            self._stream_bubble.set_plain("(no response)")
        self._stream_bubble = None
        self.generating = False
        self.send_btn.setText("Send")
        self.send_btn.setProperty("stopping", "false")
        self.send_btn.style().polish(self.send_btn)
        self._refresh_actions()
        self.app.set_status(self._stats(meta))
        self.app.schedule_save()
        self._scroll_to_bottom()

    def _stats(self, meta):
        ec, ed = meta.get("eval_count"), meta.get("eval_duration")
        if ec and ed:
            return f"{self.model} · {ec} tokens · {ec / (ed / 1e9):.0f} tok/s"
        return "Ready"

    def _refresh_actions(self):
        asst = [b for b in self._bubbles if b.role == "assistant"]
        for i, b in enumerate(asst):
            b.clear_actions()
            content = self._content_for_bubble(b)
            b.add_action("Copy", lambda _=False, c=content: self.app.copy(c))
            if i == len(asst) - 1 and not self.generating:
                b.add_action("↻ Regenerate", lambda _=False: self.regenerate())

    def _content_for_bubble(self, bubble):
        asst_bubbles = [b for b in self._bubbles if b.role == "assistant"]
        asst_msgs = [m for m in self.messages if m["role"] == "assistant"]
        try:
            return asst_msgs[asst_bubbles.index(bubble)]["content"]
        except (ValueError, IndexError):
            return ""

    def stop(self):
        if self.generating:
            self.stop_event.set()
            self.app.set_status("Stopping…")

    def clear(self):
        if self.generating:
            self.stop()
        self.messages.clear()
        for b in self._bubbles:
            b.setParent(None)
            b.deleteLater()
        self._bubbles.clear()
        self._placeholder = self._make_placeholder()
        self.col.insertWidget(0, self._placeholder)
        self.app.schedule_save()

    def set_title(self, text):
        clean = " ".join(text.split())
        self.title = (clean[:34] + "…") if len(clean) > 35 else (clean or "New chat")
        self.app.update_conversation_title(self)
        self.app.schedule_save()

    def export_markdown(self):
        lines = [f"# {self.title}", ""]
        if self.system.strip():
            lines += ["> **System:** " + self.system, ""]
        for m in self.messages:
            who = "You" if m["role"] == "user" else (self.model or "Assistant")
            lines += [f"## {who}", "", m["content"], ""]
        return "\n".join(lines)

    def serialize(self):
        return {"title": self.title, "system": self.system, "model": self.model,
                "messages": self.messages}


class ModelManager(QDialog):
    def __init__(self, app):
        super().__init__(app.win)
        self.app = app
        self.pulling = False
        self.setWindowTitle("Manage models")
        self.resize(520, 540)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        title = QLabel("Manage models")
        title.setObjectName("dialogTitle")
        v.addWidget(title)

        row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Model name, e.g. llama3.1:8b")
        self.entry.returnPressed.connect(self.pull)
        row.addWidget(self.entry, 1)
        pull_btn = QPushButton("Pull")
        pull_btn.setObjectName("primaryBtn")
        pull_btn.setCursor(Qt.PointingHandCursor)
        pull_btn.clicked.connect(self.pull)
        row.addWidget(pull_btn)
        v.addLayout(row)
        hint = QLabel("Browse names at ollama.com/library — e.g. qwen2.5-coder:7b, phi3, gemma2")
        hint.setObjectName("dialogHint")
        v.addWidget(hint)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        v.addWidget(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("dialogHint")
        self.progress_label.hide()
        v.addWidget(self.progress_label)

        installed = QLabel("Installed")
        installed.setObjectName("title")
        v.addWidget(installed)
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_inner = QWidget()
        self.list_layout = QVBoxLayout(self.list_inner)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        self.list_scroll.setWidget(self.list_inner)
        v.addWidget(self.list_scroll, 1)

        self._reload()

    def _reload(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        models = backend.list_models_detailed()
        if not models:
            empty = QLabel("No models installed yet.")
            empty.setObjectName("dialogHint")
            self.list_layout.insertWidget(0, empty)
            return
        for i, m in enumerate(models):
            row = QFrame()
            row.setObjectName("modelRow")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 8, 8)
            name = QLabel(m["name"])
            h.addWidget(name)
            size = QLabel(fmt_size(m["size"]))
            size.setObjectName("dialogHint")
            h.addWidget(size)
            h.addStretch()
            dele = QPushButton("Delete")
            dele.setObjectName("deleteBtn")
            dele.setCursor(Qt.PointingHandCursor)
            dele.clicked.connect(lambda _=False, n=m["name"]: self._delete(n))
            h.addWidget(dele)
            self.list_layout.insertWidget(i, row)

    def _delete(self, name):
        try:
            backend.delete_model(name)
            self.app.set_status(f"Deleted {name}")
        except backend.OllamaError as exc:
            self.app.set_status(str(exc))
        self._reload()
        self.app.refresh_models()

    def pull(self):
        name = self.entry.text().strip()
        if not name or self.pulling:
            return
        self.pulling = True
        self.progress.show()
        self.progress.setValue(0)
        self.progress_label.show()
        self.progress_label.setStyleSheet("")
        self.progress_label.setText(f"Pulling {name}…")
        self._signals = _PullSignals()
        self._signals.progress.connect(self._on_progress)
        self._signals.done.connect(self._on_done)
        self._signals.error.connect(self._on_error)
        threading.Thread(target=self._pull_worker, args=(name,), daemon=True).start()

    def _pull_worker(self, name):
        try:
            backend.pull_model(name, lambda u: self._signals.progress.emit(u))
            self._signals.done.emit(name)
        except backend.OllamaError as exc:
            self._signals.error.emit(str(exc))

    def _on_progress(self, u):
        total, done, status = u.get("total", 0), u.get("completed", 0), u.get("status", "")
        if total:
            pct = int(done / total * 100)
            self.progress.setValue(pct)
            self.progress_label.setText(f"{status} — {fmt_size(done)} / {fmt_size(total)} ({pct}%)")
        else:
            self.progress_label.setText(status)

    def _on_done(self, name):
        self.pulling = False
        self.progress.setValue(100)
        self.progress_label.setText(f"Pulled {name} ✓")
        self.entry.clear()
        self._reload()
        self.app.refresh_models()

    def _on_error(self, message):
        self.pulling = False
        self.progress_label.setText(message)
        self.progress_label.setStyleSheet(f"color:{PALETTE['danger']};")


class _PullSignals(QObject):
    progress = Signal(dict)
    done = Signal(str)
    error = Signal(str)


class SettingsDialog(QDialog):
    def __init__(self, app):
        super().__init__(app.win)
        self.app = app
        self.setWindowTitle("Settings")
        self.resize(460, 460)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(8)

        title = QLabel("Settings")
        title.setObjectName("dialogTitle")
        v.addWidget(title)

        v.addWidget(QLabel("Default model for new chats"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(backend.list_models())
        cur = app.settings.get("default_model", "")
        if cur and self.model_combo.findText(cur) >= 0:
            self.model_combo.setCurrentText(cur)
        v.addWidget(self.model_combo)

        v.addWidget(QLabel("Default system prompt"))
        self.system = QTextEdit()
        self.system.setAcceptRichText(False)
        self.system.setFixedHeight(90)
        self.system.setPlainText(app.settings.get("system_prompt", ""))
        v.addWidget(self.system)

        self.temp_label = QLabel(f"Temperature: {app.temperature:.2f}")
        v.addWidget(self.temp_label)
        self.temp = QSlider(Qt.Horizontal)
        self.temp.setRange(0, 150)
        self.temp.setValue(int(app.temperature * 100))
        self.temp.valueChanged.connect(
            lambda val: self.temp_label.setText(f"Temperature: {val/100:.2f}"))
        v.addWidget(self.temp)

        v.addStretch()
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        save = QPushButton("Save")
        save.setObjectName("primaryBtn")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        v.addLayout(btns)

    def _save(self):
        self.app.settings["default_model"] = self.model_combo.currentText()
        self.app.settings["system_prompt"] = self.system.toPlainText().strip()
        self.app.settings["temperature"] = round(self.temp.value() / 100, 2)
        self.app.temperature = self.app.settings["temperature"]
        storage.save_settings(self.app.settings)
        self.app.set_status("Settings saved")
        self.accept()


def fmt_size(num):
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


class ChatApp:
    def __init__(self):
        self.settings = storage.load_settings()
        self.temperature = float(self.settings.get("temperature", 0.7))
        self.conversations = []
        self.active = None
        self._rows = {}
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_now)

        self.win = QMainWindow()
        self.win.setWindowTitle("Local LLM Chat")
        self.win.resize(*self._parse_geometry())
        self.win.setMinimumSize(820, 560)
        self._build_ui()
        self.refresh_models()
        self._restore_conversations()
        self._bind_shortcuts()
        self.win.closeEvent = self._on_close

    def _parse_geometry(self):
        geo = self.settings.get("geometry", "1080x740")
        try:
            w, h = geo.lower().split("x")[:2]
            return int(w), int("".join(c for c in h if c.isdigit()))
        except Exception:
            return 1080, 740

    # ---- UI --------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(248)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(12, 16, 12, 12)
        sv.setSpacing(8)
        brand = QLabel("💬  Local Chat")
        brand.setObjectName("brand")
        sv.addWidget(brand)
        new_btn = QPushButton("＋   New chat")
        new_btn.setObjectName("newChat")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self.new_conversation)
        sv.addWidget(new_btn)

        list_scroll = QScrollArea()
        list_scroll.setWidgetResizable(True)
        list_scroll.setFrameShape(QFrame.NoFrame)
        list_scroll.setFocusPolicy(Qt.NoFocus)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_inner = QWidget()
        self.list_layout = QVBoxLayout(self.list_inner)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()
        list_scroll.setWidget(self.list_inner)
        sv.addWidget(list_scroll, 1)

        for text, cmd in (("⚙   Settings", self.open_settings),
                          ("⬢   Manage models", self.open_models)):
            b = QPushButton(text)
            b.setObjectName("footerBtn")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(cmd)
            sv.addWidget(b)
        root.addWidget(sidebar)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(56)
        hv = QHBoxLayout(header)
        hv.setContentsMargins(20, 0, 16, 0)
        self.title_label = QLabel("New chat")
        self.title_label.setObjectName("title")
        self.title_label.mouseDoubleClickEvent = lambda e: self._rename_active()
        hv.addWidget(self.title_label)
        hv.addStretch()
        sys_btn = QPushButton("System")
        sys_btn.setObjectName("headerBtn")
        sys_btn.setCursor(Qt.PointingHandCursor)
        sys_btn.clicked.connect(self.edit_system_prompt)
        hv.addWidget(sys_btn)
        export_btn = QPushButton("Export")
        export_btn.setObjectName("headerBtn")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self.export_active)
        hv.addWidget(export_btn)
        self.model_combo = QComboBox()
        self.model_combo.setObjectName("modelCombo")
        self.model_combo.currentTextChanged.connect(self._on_model_change)
        hv.addWidget(self.model_combo)
        refresh = QToolButton()
        refresh.setText("↻")
        refresh.setObjectName("headerBtn")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh_models)
        hv.addWidget(refresh)
        mv.addWidget(header)

        self.stack = QStackedWidget()
        mv.addWidget(self.stack, 1)
        root.addWidget(main, 1)

        self.win.setCentralWidget(central)
        self.status = self.win.statusBar()
        self.status.showMessage("")

    # ---- conversations ---------------------------------------------------------

    def _restore_conversations(self):
        for data in storage.load_conversations():
            conv = Conversation(self, title=data.get("title", "New chat"),
                                system=data.get("system", ""), model=data.get("model", ""),
                                messages=data.get("messages", []))
            self._register(conv, at_top=False)
        if self.conversations:
            self.show(self.conversations[0])
        else:
            self.new_conversation()

    def new_conversation(self):
        conv = Conversation(self, system=self.settings.get("system_prompt", ""),
                            model=self.current_model())
        self._register(conv, at_top=True)
        self.show(conv)
        conv.input.setFocus()
        self.schedule_save()

    def _register(self, conv, at_top):
        self.stack.addWidget(conv.page)
        if at_top:
            self.conversations.insert(0, conv)
        else:
            self.conversations.append(conv)

        row = QFrame()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        item = QPushButton(conv.title)
        item.setObjectName("chatItem")
        item.setCheckable(True)
        item.setCursor(Qt.PointingHandCursor)
        item.clicked.connect(lambda _=False, c=conv: self.show(c))
        item.mouseDoubleClickEvent = lambda e, c=conv: self._rename(c)
        h.addWidget(item, 1)
        dele = QToolButton()
        dele.setText("✕")
        dele.setObjectName("chatDelete")
        dele.setCursor(Qt.PointingHandCursor)
        dele.clicked.connect(lambda _=False, c=conv: self.delete_conversation(c))
        h.addWidget(dele)
        index = 0 if at_top else self.list_layout.count() - 1
        self.list_layout.insertWidget(index, row)
        self._rows[conv] = {"row": row, "item": item}

    def show(self, conv):
        self.active = conv
        self.stack.setCurrentWidget(conv.page)
        self.title_label.setText(conv.title)
        if conv.model and self.model_combo.findText(conv.model) >= 0:
            self.model_combo.blockSignals(True)
            self.model_combo.setCurrentText(conv.model)
            self.model_combo.blockSignals(False)
        for c, widgets in self._rows.items():
            widgets["item"].setChecked(c is conv)
        conv.input.setFocus()

    def delete_conversation(self, conv):
        if len(self.conversations) <= 1:
            conv.clear()
            conv.set_title("New chat")
            self.set_status("That's the last chat — cleared it instead.")
            return
        conv.stop()
        was_active = self.active is conv
        idx = self.conversations.index(conv)
        self.stack.removeWidget(conv.page)
        conv.page.deleteLater()
        self._rows[conv]["row"].deleteLater()
        del self._rows[conv]
        self.conversations.remove(conv)
        if was_active:
            self.show(self.conversations[min(idx, len(self.conversations) - 1)])
        self.schedule_save()

    def update_conversation_title(self, conv):
        if conv in self._rows:
            self._rows[conv]["item"].setText(conv.title)
        if self.active is conv:
            self.title_label.setText(conv.title)

    def _rename_active(self):
        if self.active:
            self._rename(self.active)

    def _rename(self, conv):
        name, ok = QInputDialog.getText(self.win, "Rename chat", "Conversation name:",
                                        text=conv.title)
        if ok and name.strip():
            conv.title = name.strip()[:44]
            self.update_conversation_title(conv)
            self.schedule_save()

    # ---- system prompt / export ------------------------------------------------

    def edit_system_prompt(self):
        if not self.active:
            return
        dialog = QDialog(self.win)
        dialog.setWindowTitle("System prompt")
        dialog.resize(460, 280)
        v = QVBoxLayout(dialog)
        v.setContentsMargins(20, 20, 20, 20)
        title = QLabel(f"System prompt for “{self.active.title}”")
        title.setObjectName("dialogTitle")
        v.addWidget(title)
        hint = QLabel("Steers the model for this conversation. Leave blank for none.")
        hint.setObjectName("dialogHint")
        v.addWidget(hint)
        text = QTextEdit()
        text.setAcceptRichText(False)
        text.setPlainText(self.active.system)
        v.addWidget(text, 1)
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(dialog.reject)
        btns.addWidget(cancel)
        save = QPushButton("Save")
        save.setObjectName("primaryBtn")

        def commit():
            self.active.system = text.toPlainText().strip()
            self.schedule_save()
            self.set_status("System prompt updated")
            dialog.accept()

        save.clicked.connect(commit)
        btns.addWidget(save)
        v.addLayout(btns)
        dialog.exec()

    def export_active(self):
        if not self.active or not self.active.messages:
            self.set_status("Nothing to export yet")
            return
        path, _ = QFileDialog.getSaveFileName(self.win, "Export conversation",
                                              f"{self.active.title[:40] or 'chat'}.md",
                                              "Markdown (*.md);;Text (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.active.export_markdown())
            self.set_status(f"Exported to {path}")
        except OSError as exc:
            self.set_status(f"Export failed: {exc}")

    def open_settings(self):
        SettingsDialog(self).exec()

    def open_models(self):
        ModelManager(self).exec()

    # ---- models ----------------------------------------------------------------

    def refresh_models(self):
        models = backend.list_models()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            self.model_combo.setEnabled(True)
            current = self.settings.get("default_model", "") or models[0]
            if current not in models:
                current = models[0]
            self.model_combo.setCurrentText(current)
            self.set_status(f"{len(models)} model(s) installed · {current}")
        else:
            self.model_combo.setEnabled(False)
            if backend.is_running():
                self.set_status("No models installed — open Manage models to pull one")
            else:
                self.set_status("Ollama not reachable — start it with 'ollama serve', then ↻")
        self.model_combo.blockSignals(False)

    def current_model(self):
        return self.model_combo.currentText().strip() if self.model_combo.isEnabled() else ""

    def _on_model_change(self, _text):
        if self.active:
            self.active.model = self.current_model()
            self.schedule_save()

    # ---- misc ------------------------------------------------------------------

    def copy(self, text):
        QGuiApplication.clipboard().setText(text)
        self.set_status("Copied to clipboard")

    def set_status(self, text):
        self.status.showMessage(text)

    def schedule_save(self):
        self._save_timer.start(600)

    def _save_now(self):
        storage.save_conversations([c.serialize() for c in self.conversations])

    def _bind_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self.win, self.new_conversation)
        QShortcut(QKeySequence("Ctrl+E"), self.win, self.export_active)
        QShortcut(QKeySequence("Ctrl+R"), self.win, lambda: self.active and self.active.regenerate())
        QShortcut(QKeySequence("Ctrl+,"), self.win, self.open_settings)
        QShortcut(QKeySequence("Escape"), self.win, lambda: self.active and self.active.stop())

    def _on_close(self, event):
        self.settings["geometry"] = f"{self.win.width()}x{self.win.height()}"
        storage.save_settings(self.settings)
        storage.save_conversations([c.serialize() for c in self.conversations])
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    chat = ChatApp()
    chat.win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
