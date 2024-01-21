import tkinter as tk
from tkinter import ttk, filedialog
from ttkthemes import ThemedTk
import requests
import json

def get_api_key():
    with open("api.key", "r") as key_file:
        api_key = key_file.read().strip()
    return api_key

API_TOKEN = get_api_key()

class HuggingFaceGUI:
    def __init__(self, root):
        self.root = root
        self.root.set_theme("arc")
        self.root.title("Hugging Face Inference API GUI")

        self.model_options = [
            "bert-base-uncased", "facebook/bart-large-cnn", "deepset/roberta-base-squad2",
            "google/tapas-base-finetuned-wtq", "sentence-transformers/all-MiniLM-L6-v2",
            "distilbert-base-uncased-finetuned-sst-2-english", "gpt2"
        ]

        self.create_widgets()

    def create_widgets(self):
        self.model_label = tk.Label(self.root, text="Select Model:")
        self.model_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        self.model_var = tk.StringVar()
        self.model_var.set(self.model_options[0])

        self.model_dropdown = ttk.Combobox(self.root, textvariable=self.model_var, values=self.model_options)
        self.model_dropdown.grid(row=0, column=1, padx=10, pady=5, columnspan=2)

        model_description_label = tk.Label(self.root, text="Model Description:")
        model_description_label.grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)

        model_description_text = tk.Text(self.root, height=6, width=50, state=tk.DISABLED)
        model_description_text.grid(row=1, column=1, padx=10, pady=5, columnspan=2)

        self.model_dropdown.bind("<<ComboboxSelected>>", lambda event: self.update_model_description(model_description_text))

        self.input_label = tk.Label(self.root, text="Input:")
        self.input_label.grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)

        self.input_text = tk.Text(self.root, height=6, width=50)
        self.input_text.grid(row=2, column=1, padx=10, pady=5, columnspan=2)

        self.browse_button = tk.Button(self.root, text="Browse", command=self.browse_file)
        self.browse_button.grid(row=3, column=0, padx=10, pady=5)

        self.output_label = tk.Label(self.root, text="Output:")
        self.output_label.grid(row=4, column=0, padx=10, pady=5, sticky=tk.W)

        self.output_text = tk.Text(self.root, height=6, width=50, state=tk.DISABLED)
        self.output_text.grid(row=4, column=1, padx=10, pady=5, columnspan=2)

        self.send_button = tk.Button(self.root, text="Send", command=self.send_request)
        self.send_button.grid(row=5, column=0, columnspan=3, pady=10)

        self.status_label = tk.Label(self.root, text="", fg="red")
        self.status_label.grid(row=6, column=0, columnspan=3)

    def update_model_description(self, model_description_text):
        selected_model = self.model_var.get()
        model_description = f"Custom description for {selected_model}"
        model_description_text.config(state=tk.NORMAL)
        model_description_text.delete("1.0", tk.END)
        model_description_text.insert(tk.END, model_description)
        model_description_text.config(state=tk.DISABLED)

    def browse_file(self):
        try:
            file_path = filedialog.askopenfilename()
            if file_path:
                with open(file_path, "r") as file:
                    content = file.read()
                    self.input_text.delete("1.0", tk.END)
                    self.input_text.insert(tk.END, content)
        except Exception as e:
            error_message = f"Error reading file: {str(e)}"
            self.show_error_message(error_message)

    def send_request(self):
        self.status_label.config(text="Sending request...", fg="blue")
        self.root.update_idletasks()

        selected_model = self.model_var.get()
        input_text = self.input_text.get("1.0", tk.END).strip()

        if input_text and not input_text.isspace():
            api_url = f"https://api-inference.huggingface.co/models/{selected_model}"
            headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
            payload = {"inputs": [input_text]}

            try:
                response_data = self.query_huggingface_api(api_url, headers, payload)
                formatted_response = json.dumps(response_data, indent=2)
                self.show_output(formatted_response)
            except requests.exceptions.RequestException as e:
                error_message = f"Request error: {str(e)}"
                self.show_error_message(error_message)
        else:
            self.show_error_message("Please enter valid input text")

        self.status_label.config(text="", fg="red")

    def show_output(self, formatted_response):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)

        try:
            response_data = json.loads(formatted_response)
            generated_text = response_data[0][0]["generated_text"]
            self.output_text.insert(tk.END, generated_text)
        except (json.JSONDecodeError, KeyError, IndexError):
            self.output_text.insert(tk.END, "Error: Unable to extract generated text from the response")

        self.output_text.config(state=tk.DISABLED)

    def show_error_message(self, error_message):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, f"Error: {error_message}")
        self.output_text.config(state=tk.DISABLED)

    @staticmethod
    def query_huggingface_api(api_url, headers, payload):
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

if __name__ == "__main__":
    try:
        root = ThemedTk()
        app = HuggingFaceGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"An error occurred: {e}")
