import tkinter as tk
from tkinter import ttk, filedialog
import requests
import json
import asyncio 
from tkinter.font import Font

from requestLocal import query_ollama

class GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Chat Assistant")
        self.root.configure(bg='#2b2b2b')
        
        # Define colors and fonts
        self.colors = {
            'bg': '#2b2b2b',
            'fg': '#000000',  # Changed to black
            'input_bg': '#ffffff',  # Changed to white for better contrast
            'button_bg': '#4a4a4a',
            'accent': '#007acc'
        }
        
        self.fonts = {
            'main': Font(family="Segoe UI", size=10),
            'chat': Font(family="Segoe UI", size=11),
            'input': Font(family="Segoe UI", size=10)
        }
        
        self.model_var = tk.StringVar(value="llama2")
        self.status_var = tk.StringVar(value="")  # Add status variable
        self.setup_styles()
        self.create_widgets()

    def setup_styles(self):
        style = ttk.Style()
        style.configure('Custom.TNotebook', background=self.colors['bg'])
        style.configure('Custom.TFrame', background=self.colors['bg'])
        style.configure('Custom.TButton',
                       background=self.colors['button_bg'],
                       foreground='#000000',  # Changed to black
                       padding=5)
        style.configure('Custom.TEntry',
                       fieldbackground=self.colors['input_bg'],
                       foreground='#000000')  # Changed to black

    def create_widgets(self):
        # Create main container
        main_container = ttk.Frame(self.root, style='Custom.TFrame')
        main_container.pack(fill='both', expand=True, padx=10, pady=10)

        # Create top control panel
        control_panel = ttk.Frame(main_container, style='Custom.TFrame')
        control_panel.pack(fill='x', pady=(0, 10))

        # Add model selector
        models = ['llama2', 'llama3:8b', 'llama3.1:8b', 'codellama']  # added new models
        model_label = ttk.Label(control_panel, text="Model:", foreground='#000000')  # Changed to black
        model_label.pack(side='left', padx=(0, 5))
        model_dropdown = ttk.Combobox(control_panel, textvariable=self.model_var, values=models, width=15)
        model_dropdown.pack(side='left', padx=5)

        # Add status label
        self.status_label = ttk.Label(
            control_panel, 
            textvariable=self.status_var, 
            foreground='#007acc',
            background=self.colors['bg']
        )
        self.status_label.pack(side='right', padx=5)

        # Add buttons with improved styling
        self.add_tab_button = ttk.Button(control_panel, text="New Chat", style='Custom.TButton', command=self.add_tab)
        self.add_tab_button.pack(side='left', padx=5)
        
        self.delete_tab_button = ttk.Button(control_panel, text="Delete Chat", style='Custom.TButton', command=self.delete_tab)
        self.delete_tab_button.pack(side='left', padx=5)

        # Create notebook with custom styling
        self.notebook = ttk.Notebook(main_container, style='Custom.TNotebook')
        self.notebook.pack(fill='both', expand=True)
        
        # Add initial tab
        self.add_tab()

    def add_tab(self):
        tab = ttk.Frame(self.notebook, style='Custom.TFrame')
        
        # Create chat container
        chat_container = ttk.Frame(tab, style='Custom.TFrame')
        chat_container.pack(fill='both', expand=True, padx=5, pady=5)

        # Create chat log with custom styling
        chat_log = tk.Text(chat_container,
                          font=self.fonts['chat'],
                          bg=self.colors['input_bg'],
                          fg='#000000',  # Changed to black
                          wrap='word',
                          state='disabled')
        chat_log.pack(fill='both', expand=True, pady=(0, 5))

        # Create input container
        input_container = ttk.Frame(chat_container, style='Custom.TFrame')
        input_container.pack(fill='x', pady=(5, 0))

        # Create input field with custom styling
        user_input = ttk.Entry(input_container,
                              font=self.fonts['input'],
                              style='Custom.TEntry')
        user_input.pack(fill='x', side='left', expand=True, padx=(0, 5))
        
        # Add send button
        send_button = ttk.Button(input_container,
                                text="Send",
                                style='Custom.TButton',
                                command=lambda: self.send_request(chat_log, user_input))
        send_button.pack(side='right')

        # Bind enter key to send
        user_input.bind('<Return>', lambda event: self.send_request(chat_log, user_input))

        self.notebook.add(tab, text=f"Chat {self.notebook.index('end') + 1}")

    def delete_tab(self):
        current_tab = self.notebook.select()
        if self.notebook.index(current_tab) > 0:
            self.notebook.forget(current_tab)

    def send_request(self, chat_log, user_input):
        selected_model = self.model_var.get()
        input_text = user_input.get().strip()

        if input_text and not input_text.isspace():
            self.status_var.set("Processing request...")
            response_data = query_ollama(selected_model, input_text)
            
            if 'error' in response_data:
                if "downloading" in response_data['error'].lower():
                    self.status_var.set("Downloading model... This may take several minutes depending on your internet and storage speed.")
                    # You might want to implement a retry mechanism here
                else:
                    self.show_error_message(chat_log, response_data['error'])
                    self.status_var.set("")
            else:
                formatted_response = json.dumps(response_data, indent=2)
                self.show_output(chat_log, formatted_response)
                self.status_var.set("")
        else:
            self.show_error_message(chat_log, "Please enter valid input text")
            self.status_var.set("")

        user_input.delete(0, 'end')
    

    def show_output(self, chat_log, formatted_response):
        chat_log.config(state='normal')
        chat_log.tag_configure('assistant', foreground='#000000')  # Changed to black
        chat_log.tag_configure('response', foreground='#000000')  # Changed to black
        chat_log.tag_configure('error', foreground='#ff0000')  # Keep errors in red for visibility
        chat_log.insert('end', "\n🤖 Assistant: ", 'assistant')
        chat_log.insert('end', formatted_response + '\n', 'response')
        chat_log.see('end')
        chat_log.config(state='disabled')

    def show_error_message(self, chat_log, error_message):
        chat_log.config(state='normal')
        chat_log.insert('end', f"⚠️ Error: {error_message}\n", 'error')
        chat_log.see('end')
        chat_log.config(state='disabled')

    @staticmethod
    def query_huggingface_api(api_url, headers, payload):
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

root = tk.Tk()
app = GUI(root)
root.mainloop()