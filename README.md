# Local LLM Chat GUI

A simple Python-based GUI application that allows you to interact with local Large Language Models through Ollama. This application provides a chat interface with multiple tabs for different conversations.

## Features

- Multiple chat tabs support
- Local LLM integration via Ollama
- Simple and intuitive interface
- Real-time responses
- Error handling and status messages

## Prerequisites

Before using this application, you need to:

1. Install Ollama on your system
   - Visit [Ollama's website](https://ollama.ai/) to download and install
   - Make sure the Ollama service is running

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone [your-repository-url]
   cd ChatGPT-GUI
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start Ollama service on your system

2. Run the application:
   ```bash
   python chatGPT.py
   ```

3. Using the Interface:
   - Click "New Chat" to open a new chat tab
   - Type your message and press Enter to send
   - Use "Delete Chat" to remove the current tab
   - The default model is "llama2" but can be modified in the code

## Technical Details

The application is built using:
- Python 3.x
- Tkinter for GUI
- Ollama for local LLM integration
- Asynchronous request handling

### Project Structure
```
ChatGPT-GUI/
├── chatGPT.py       # Main GUI application
├── requestLocal.py  # Ollama integration
└── requirements.txt # Python dependencies
```

## Error Handling

The application handles common errors including:
- Ollama service not running
- Model not found/not downloaded
- Invalid inputs
- Connection issues

## Troubleshooting

1. If you get "Ollama server is not running" error:
   - Check if Ollama is installed
   - Verify Ollama service is running
   - Restart Ollama service

2. If model responses are slow:
   - Check your system resources
   - Consider using a lighter model

## Contributing

Feel free to submit issues and enhancement requests!
