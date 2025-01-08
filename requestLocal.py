import ollama
from typing import Dict, Any

def check_ollama_status() -> bool:
    try:
        # Simple test query to check if Ollama is running
        ollama.list()
        return True
    except Exception:
        return False

def ensure_model_exists(model: str) -> Dict[str, Any]:
    try:
        # Check if model exists in local models
        models = ollama.list()
        if not any(m.get('name') == model for m in models['models']):
            print(f"Model {model} not found. Attempting to pull...")
            ollama.pull(model)
            return {"status": "success", "message": f"Model {model} pulled successfully"}
        return {"status": "success", "message": f"Model {model} already exists"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to pull model: {str(e)}"}

def query_ollama(model: str, prompt: str) -> Dict[str, Any]:
    if not check_ollama_status():
        return {"error": "Ollama server is not running. Please start Ollama first."}

    # Check and pull model if necessary
    model_status = ensure_model_exists(model)
    if model_status["status"] == "error":
        return {"error": model_status["message"]}

    try:
        response = ollama.chat(model=model, messages=[
            {
                'role': 'user',
                'content': prompt
            }
        ])
        return {
            'response': response.message.content,
            'model': model,
            'prompt': prompt
        }
    except ollama.ResponseError as e:
        return {"error": f"Ollama error: {e.error}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

# Test the function
if __name__ == "__main__":
    if check_ollama_status():
        response = query_ollama("llama2", "What's a cow?")
        print(response)
    else:
        print("Error: Ollama server is not running")