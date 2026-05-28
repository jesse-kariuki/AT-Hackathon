import requests
import urllib3

# Ignore Hackathon Wi-Fi blocks
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("Starting Sandbox Authentication Test...")

url = "https://api.sandbox.africastalking.com/version1/messaging"

headers = {
    "Accept": "application/json",
    # PASTE YOUR KEY INSIDE THESE QUOTES:
    "apiKey": "atsk_848360bb9c713f2971bc4c3a38bdaeff3823ab43ed12ddd9451e86b9b46220adfbe522e9" 
}

data = {
    "username": "sandbox",
    "to": "+254704784613",
    "message": "🚨 NUCLEAR TEST SUCCESSFUL! 🚨"
}

try:
    response = requests.post(url, headers=headers, data=data, verify=False)
    print("\n--- RESULT ---")
    print(response.text)
    print("--------------\n")
except Exception as e:
    print("Network Error:", e)