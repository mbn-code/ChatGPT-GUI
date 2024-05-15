import tkinter as tk
from tkinter import ttk, filedialog
import requests
import json
import asyncio 

from requestLocal import query_ollama


class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Local Chatbot GUI")

        self.model_var = tk.StringVar(value="llama2")

        self.create_widgets()

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)

        self.add_tab_button = ttk.Button(self.root, text="New Chat", command=self.add_tab)
        self.add_tab_button.pack(side='left')

        self.delete_tab_button = ttk.Button(self.root, text="Delete Chat", command=self.delete_tab)
        self.delete_tab_button.pack(side='right')

    def add_tab(self):
        tab = ttk.Frame(self.notebook)

        chat_log = tk.Text(tab, state='disabled')
        chat_log.pack(fill='both', expand=True)

        user_input = ttk.Entry(tab)
        user_input.pack(fill='x')
        user_input.bind('<Return>', lambda event: self.send_request(chat_log, user_input))

        self.notebook.add(tab, text="Chat")

    def delete_tab(self):
        current_tab = self.notebook.select()
        if self.notebook.index(current_tab) > 0:
            self.notebook.forget(current_tab)

    def send_request(self, chat_log, user_input):
        selected_model = self.model_var.get()
        input_text = user_input.get().strip()

        if input_text and not input_text.isspace():
            response_data = query_ollama(selected_model, input_text)
            if 'error' in response_data:
                self.show_error_message(chat_log, response_data['error'])
            else:
                formatted_response = json.dumps(response_data, indent=2)
                self.show_output(chat_log, formatted_response)
        else:
            self.show_error_message(chat_log, "Please enter valid input text")

        user_input.delete(0, 'end')
    

    def show_output(self, chat_log, formatted_response):
        chat_log.config(state='normal')
        chat_log.insert('end', formatted_response + '\n')
        chat_log.config(state='disabled')

    def show_error_message(self, chat_log, error_message):
        chat_log.config(state='normal')
        chat_log.insert('end', f"Error: {error_message}\n")
        chat_log.config(state='disabled')

    @staticmethod
    def query_huggingface_api(api_url, headers, payload):
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

root = tk.Tk()
app = GUI(root)
root.mainloop()