import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load API Key
load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

# Read discharge summary
with open("data/discharge_summary.txt", "r") as file:
    discharge_text = file.read()

# Gemini Model
model = genai.GenerativeModel("gemini-2.5-flash")

prompt = f"""
Extract patient information from the discharge summary.

Return ONLY in this format:

Name:
Diagnosis:
Medications:
Diet:
Followup:

Discharge Summary:
{discharge_text}
"""

response = model.generate_content(prompt)

print(response.text)