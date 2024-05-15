import requests
import json

def query_ollama(model, prompt):
    url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()  # Raises an HTTPError if the status is 4xx, 5xx

    return response['response']

response = query_ollama("llama3", "What's a cow?")
print(response['response'])