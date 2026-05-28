import requests
import urllib3

# Ignore Hackathon Wi-Fi blocks
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("Starting Sandbox Authentication Test...")

url = "https://api.sandbox.africastalking.com/version1/messaging"

headers = {
    "Accept": "application/json",
    # PASTE YOUR KEY INSIDE THESE QUOTES:
    "apiKey": "atsk_c3c4814a4c3df2806bf187391d6ce2aa8fefd2841af21234826aae429b51752128509960" 
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