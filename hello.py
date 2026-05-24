import os
from dotenv import load_dotenv
from google import genai

# Load the API key from .env
load_dotenv()

# Create the client — it picks up GEMINI_API_KEY automatically
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Send one message to Gemini
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello and tell me one fun fact about learning.",
)

print(response.text)