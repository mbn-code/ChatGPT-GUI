import tkinter as tk
import openai

# Set up API key

openai.api_key = ""

# Create a function to make the API request and return the response
def get_response(query):
    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=query,
        max_tokens=1024,
        n=1,
        stop=None,
        temperature=0.5
    )
    return response["choices"][0]["text"]

# Create a Tkinter app
# Create a Tkinter app
app = tk.Tk()
app.title("OpenAI Chat GPT")

app.geometry("432x195")

# Create a label for the token input
token_label = tk.Label(app, text="API Key:")
token_label.grid(row=0, column=0, padx=10, pady=10)

# Create a text entry box for the API key
token_text = tk.StringVar()
token_box = tk.Entry(app, textvariable=token_text)
token_box.grid(row=0, column=1, padx=10, pady=10)

# Create a button to submit the token
def submit_token():
    openai.api_key = token_text.get()
submit_token_button = tk.Button(app, text="Set Token", command=submit_token)
submit_token_button.grid(row=0, column=2, padx=10, pady=10)

# Create a text entry box for the user's query
query_text = tk.StringVar()
query_box = tk.Entry(app, textvariable=query_text)
query_box.grid(row=1, column=0, columnspan=3, padx=10, pady=10)

# Create a button to submit the query
def submit_query():
    query = query_text.get()
    response = get_response(query)
    response_label.config(text=response)

submit_label = tk.Label(app, text="Submit")
submit_label.grid(row=1, column=0)

submit_button = tk.Button(app, text="Submit", command=submit_query)
submit_button.grid(row=1, column=2)

# Create a label to display the response
response_label = tk.Label(app, text="")
response_label.grid()

# Create a button to clear the response label
def clear_response():
    response_label.config(text="")
clear_button = tk.Button(app, text="Clear Answers", command=clear_response)
clear_button.grid(column=1)



# Run the app
app.mainloop()
