# Local LLM Chat

A small, no-frills desktop chat client for local language models served by
[Ollama](https://ollama.com/). It runs entirely on your machine — no API keys,
no cloud, nothing leaves your computer.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![GUI](https://img.shields.io/badge/gui-tkinter-green)

## Features

- **Modern chat UI** — a sidebar of conversations, message bubbles aligned by
  sender, and a clean dark theme.
- **Streaming replies** — text appears token by token as the model generates it.
- **Non-blocking UI** — model calls run on a background thread, so the window
  never freezes while you wait. The Send button turns into **Stop** mid-reply.
- **Real conversations** — each chat keeps its full history, so the model
  remembers the thread (not just your last message). Chats are auto-titled from
  your first message.
- **Multiple chats** — start as many as you like from the sidebar and switch
  between them; each is independent.
- **Models read from your system** — the picker is populated from whatever you
  actually have installed (`ollama list`); nothing is hardcoded. Pull a new
  model and hit **↻** to see it.

## Requirements

- **Python 3.9+** with Tkinter (bundled with the python.org installer; on Linux
  install `python3-tk`).
- **[Ollama](https://ollama.com/download)** installed and running, with at least
  one model pulled.

## Setup

```bash
# 1. Clone
git clone https://github.com/mbn-code/ChatGPT-GUI.git
cd ChatGPT-GUI

# 2. (recommended) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Make sure Ollama is running and you have a model
ollama serve                     # if it isn't already running
ollama pull llama3.1:8b          # or any model you like
```

## Run

```bash
python chatGPT.py
```

Then:

- Pick a model from the dropdown in the top bar (use **↻** to refresh the list).
- Type a message and press **Enter** to send; **Shift+Enter** for a newline.
- While a reply streams, the **Send** button becomes **Stop** — click it to cut
  the reply short.
- Use **＋ New chat** in the sidebar to start another conversation, click a chat
  to switch to it, and the **✕** next to a chat to delete it.

### Connecting to a remote Ollama host

By default the app talks to `http://localhost:11434`. To point it elsewhere,
set the standard Ollama environment variable before launching:

```bash
OLLAMA_HOST=http://192.168.1.50:11434 python chatGPT.py
```

## Project structure

```
ChatGPT-GUI/
├── chatGPT.py        # Tkinter GUI: tabs, streaming, threading
├── requestLocal.py   # Ollama backend: model list + streaming chat
└── requirements.txt  # Python dependencies
```

`requestLocal.py` can also be run on its own as a quick connectivity check:

```bash
python requestLocal.py
```

## Troubleshooting

- **"Ollama not reachable"** — make sure `ollama serve` is running, then click
  **Refresh**.
- **"Model isn't installed"** — pull it first: `ollama pull <model>`, then
  **Refresh** the model list.
- **Replies are slow** — that's the model, not the app. Try a smaller model
  (e.g. `llama3.1:8b` instead of a 70B model) or check your system resources.
- **No window appears / `ModuleNotFoundError: tkinter`** — install Tkinter
  (`python3-tk` on Debian/Ubuntu, included with the python.org macOS/Windows
  installers).

## Contributing

Issues and pull requests are welcome.
