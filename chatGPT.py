import tkinter as tk
from tkinter import ttk, filedialog
import requests
import json

API_TOKEN = "YOUR_API_TOKEN_HERE"

class HuggingFaceGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hugging Face Inference API GUI")

        # Model options
        self.model_options = [
            "facebook/detr-resnet-50-panoptic",
            "facebook/detr-resnet-50",
            "google/vit-base-patch16-224",
            "superb/hubert-large-superb-er",
            "facebook/wav2vec2-base-960h"
        ]

        # GUI components
        self.create_widgets()

    def create_widgets(self):
        # Model selection
        self.model_label = tk.Label(self.root, text="Select Model:")
        self.model_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        self.model_var = tk.StringVar()
        self.model_var.set(self.model_options[0])

        self.model_dropdown = ttk.Combobox(self.root, textvariable=self.model_var, values=self.model_options)
        self.model_dropdown.grid(row=0, column=1, padx=10, pady=5, columnspan=2)

        # Input section
        self.input_label = tk.Label(self.root, text="Input:")
        self.input_label.grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)

        self.input_text = tk.Text(self.root, height=6, width=50)
        self.input_text.grid(row=1, column=1, padx=10, pady=5, columnspan=2)

        self.browse_button = tk.Button(self.root, text="Browse", command=self.browse_file)
        self.browse_button.grid(row=2, column=0, padx=10, pady=5)

        # Output section
        self.output_label = tk.Label(self.root, text="Output:")
        self.output_label.grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)

        self.output_text = tk.Text(self.root, height=6, width=50, state=tk.DISABLED)
        self.output_text.grid(row=3, column=1, padx=10, pady=5, columnspan=2)

        # Send button
        self.send_button = tk.Button(self.root, text="Send", command=self.send_request)
        self.send_button.grid(row=4, column=0, columnspan=3, pady=10)

    def browse_file(self):
        try:
            file_path = filedialog.askopenfilename()
            if file_path:
                with open(file_path, "r") as file:
                    content = file.read()
                    self.input_text.delete(1.0, tk.END)
                    self.input_text.insert(tk.END, content)
        except Exception as e:
            error_message = f"Error reading file: {str(e)}"
            self.show_error_message(error_message)

    def send_request(self):
        selected_model = self.model_var.get()
        input_text = self.input_text.get("1.0", tk.END).strip()  # Adjusted this line

        if input_text and not input_text.isspace():
            api_url = f"https://api-inference.huggingface.co/models/{selected_model}"
            headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
            payload = {"inputs": [input_text]}

            print("API URL:", api_url)
            print("Headers:", headers)
            print("Payload:", payload)

            try:
                response_data = self.query_huggingface_api(api_url, headers, payload)
                formatted_response = json.dumps(response_data, indent=2)
                self.show_output(formatted_response)
            except requests.exceptions.RequestException as e:
                error_message = f"Request error: {str(e)}"
                self.show_error_message(error_message)
        else:
            self.show_error_message("Please enter valid input text.")

    def show_output(self, formatted_response):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, formatted_response)
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
    root = tk.Tk()
    app = HuggingFaceGUI(root)
    root.mainloop()
