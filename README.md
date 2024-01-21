# Hugging Face Inference API GUI

This is a simple graphical user interface (GUI) application that allows you to interact with the Hugging Face Inference API. It enables you to send text or browse a file containing text to Hugging Face models for various natural language processing tasks.

## Prerequisites

Before using this application, you need to obtain an API key from Hugging Face. This key should be stored in a file named `api.key` in the same directory as this script.

## Installation and Usage

1. Clone the repository or download the `chatGPT.py` script to your local machine.
2. Make sure you have Python and the required libraries installed. You can install these libraries using `pip`:


   ```bash
   pip install ttkthemes requests
   ```

3. create a api.key file
   
4. Place your Hugging Face API key in a file named `api.key` in the same directory as `chatGPT.py`.
  
5. Run the script:

   ```bash
   python chatGPT.py
   ```

### Model Selection

You can select the Hugging Face model you want to use from a dropdown list. The available options are:

- facebook/detr-resnet-50-panoptic
- facebook/detr-resnet-50
- google/vit-base-patch16-224
- superb/hubert-large-superb-er
- facebook/wav2vec2-base-960h
- sentence-transformers/all-MiniLM-L6-v2
- distilbert-base-uncased-finetuned-sst-2-english
- gpt2


### Input Text

You can provide input text by either typing it directly into the text box or by clicking the "Browse" button to select a text file. The text should be in a format suitable for the selected model's input requirements.

### Send Request

Click the "Send" button to send the input text to the selected Hugging Face model. The application will then make a request to the Hugging Face Inference API with your API key and the chosen model. The response will be displayed in the "Output" section of the GUI.

### Output Display

The response from the API will be displayed in the "Output" text box. If there is an error during the API request, an error message will be displayed instead.

## Troubleshooting

- Make sure you have a valid API key in the `api.key` file.
- Ensure that you have an internet connection to access the Hugging Face Inference API.
- Check for any potential errors or exceptions displayed in the output.

## Disclaimer

This application is a simple example and may require further customization to fit your specific use case or to work with other Hugging Face models. It is recommended to refer to the Hugging Face documentation for more details on the models and API usage.

Please use this application responsibly and in accordance with Hugging Face's terms and conditions.
