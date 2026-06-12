# Local LLM Chat

A polished desktop chat client for local language models served by
[Ollama](https://ollama.com/). It runs entirely on your machine — no API keys,
no cloud, nothing leaves your computer.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![GUI](https://img.shields.io/badge/gui-tkinter-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

## Features

- **Modern chat UI** — a sidebar of saved conversations, message bubbles aligned
  by sender, and a clean dark theme.
- **Markdown & code rendering** — replies render with headings, bold/italic,
  lists, and fenced **code blocks** that get a language label and a one-click
  **Copy** button.
- **Streaming replies** — text appears token by token, on a background thread,
  so the window never freezes. The Send button becomes **Stop** mid-reply.
- **Real conversations** — each chat keeps its full history, so the model
  remembers the thread. Chats auto-title from your first message and you can
  rename them (double-click the title).
- **Saved between sessions** — conversations and settings are written to disk
  and restored when you reopen the app.
- **Regenerate** the last reply, **copy** any message, and **export** a
  conversation to Markdown.
- **Per-chat system prompt** — steer the model for a specific conversation.
- **Built-in model manager** — list, delete, and **pull new models with a live
  download progress bar**, without leaving the app.
- **Models read from your system** — the picker reflects whatever you actually
  have installed (`ollama list`); nothing is hardcoded.
- **Settings** — default model, default system prompt, and temperature.
- **Generation stats** — token count and tokens/sec shown after each reply.

## Requirements

- **Python 3.9+** with Tkinter (bundled with the python.org installer; on Linux
  install `python3-tk`).
- **[Ollama](https://ollama.com/download)** installed and running, with at least
  one model pulled (or pull one from inside the app).

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

# 4. Make sure Ollama is running
ollama serve                     # if it isn't already running
```

You don't need to pull a model from the terminal — open **Manage models** in the
app and pull one there (e.g. `llama3.1:8b`).

## Run

```bash
python chatGPT.py
```

### Using it

| Action                    | How                                                   |
| ------------------------- | ----------------------------------------------------- |
| Send a message            | type, then **Enter** (**Shift+Enter** for a newline)  |
| Stop a streaming reply    | click **Stop**, or press **Esc**                      |
| New conversation          | **＋ New chat**, or **Ctrl/Cmd+N**                    |
| Rename a chat             | double-click its title                                |
| Delete a chat             | the **✕** next to it in the sidebar                   |
| Regenerate last reply     | **↻ Regenerate** under the message, or **Ctrl/Cmd+R** |
| Copy a reply / code block | **Copy** under the message / on the code block        |
| Export to Markdown        | **Export**, or **Ctrl/Cmd+E**                         |
| Per-chat system prompt    | **System** in the top bar                             |
| Pull / delete models      | **Manage models** in the sidebar                      |
| Settings                  | **Settings**, or **Ctrl/Cmd+,**                       |

### Connecting to a remote Ollama host

By default the app talks to `http://localhost:11434`. To point it elsewhere,
set the standard Ollama environment variable before launching:

```bash
OLLAMA_HOST=http://192.168.1.50:11434 python chatGPT.py
```

### Where your data lives

Conversations and settings are stored as JSON under your platform's data dir
(`$XDG_DATA_HOME/local-llm-chat`, `~/.local/share/local-llm-chat`, or
`%APPDATA%\local-llm-chat`). Delete that folder to reset the app.

## Project structure

```
ChatGPT-GUI/
├── chatGPT.py        # Tkinter GUI: sidebar, bubbles, streaming, dialogs
├── requestLocal.py   # Ollama backend: models, streaming chat, pull/delete
├── mdrender.py       # Markdown → Tkinter Text rendering
├── storage.py        # Conversation & settings persistence
└── requirements.txt  # Python dependencies
```

`requestLocal.py` can also be run on its own as a quick connectivity check:

```bash
python requestLocal.py
```

## Troubleshooting

- **"Ollama not reachable"** — make sure `ollama serve` is running, then click
  **↻**.
- **No models / "Model isn't installed"** — open **Manage models** and pull one
  (e.g. `llama3.1:8b`).
- **Replies are slow** — that's the model, not the app. Try a smaller model or
  check your system resources.
- **No window appears / `ModuleNotFoundError: tkinter`** — install Tkinter
  (`python3-tk` on Debian/Ubuntu, included with the python.org macOS/Windows
  installers).

## License

[MIT](LICENSE)

## Contributing

Issues and pull requests are welcome.
