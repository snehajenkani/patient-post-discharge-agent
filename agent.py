import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load API key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.5-flash")

# Patient Data
patient_data = {
    "name": "Shravan",
    "diagnosis": "Appendix Surgery",
    "medications": [
        "Paracetamol - Twice Daily",
        "Antibiotic - After Food"
    ],
    "followup_date": "10 June 2026",
    "diet": "Soft foods, avoid spicy food"
}

# Tools
def get_medications():
    return "\n".join(patient_data["medications"])

def get_diet():
    return patient_data["diet"]

def get_followup():
    return patient_data["followup_date"]

# Emergency Keywords
emergency_keywords = [
    "chest pain",
    "difficulty breathing",
    "can't breathe",
    "severe bleeding",
    "unconscious"
]

print("Patient AI Agent Started!")
print("Type 'exit' to quit.\n")

while True:
    user_input = input("You: ")

    if user_input.lower() == "exit":
        print("Goodbye!")
        break

    message = user_input.lower()

    # Emergency Detection
    if any(keyword in message for keyword in emergency_keywords):
        print("\n⚠️ EMERGENCY DETECTED")
        print("Please contact your doctor immediately.\n")
        continue

    # Medication Tool
    if "medicine" in message or "medication" in message:
        print("\nAgent:")
        print(get_medications())
        print()
        continue

    # Diet Tool
    if "diet" in message or "food" in message:
        print("\nAgent:")
        print(get_diet())
        print()
        continue

    # Follow-up Tool
    if "followup" in message or "appointment" in message:
        print("\nAgent:")
        print("Your follow-up date is:", get_followup())
        print()
        continue

    # Gemini AI Response
    prompt = f"""
You are a Patient Post-Discharge Assistant.

Patient Details:
Name: {patient_data['name']}
Diagnosis: {patient_data['diagnosis']}

Responsibilities:
- Answer patient questions.
- Explain medications.
- Explain recovery instructions.
- Suggest follow-up care.
- Never diagnose diseases.
- Recommend contacting a doctor for serious symptoms.

Patient Message:
{user_input}
"""

    response = model.generate_content(prompt)

    print("\nAgent:", response.text)
    print()