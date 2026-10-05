import os
import time
import requests

API_KEY = "22b426a760d843d9bc9b402c471691aa"

headers = {
    "authorization": API_KEY
}



arquivo = "possoligar.mp3"

with open(arquivo, "rb") as f:
    response = requests.post(
        "https://api.assemblyai.com/v2/upload",
        headers=headers,
        data=f
    )

response.raise_for_status()

upload_data = response.json()
audio_url = upload_data["upload_url"]

print("Upload realizado!")
print(audio_url)



response = requests.post(
    "https://api.assemblyai.com/v2/transcript",
    headers={
        "authorization": API_KEY,
        "content-type": "application/json"
    },
    json={
        "audio_url": audio_url
    }
)

response.raise_for_status()

transcript_data = response.json()
transcript_id = transcript_data["id"]

print("Transcrição iniciada:", transcript_id)




while True:

    response = requests.get(
        f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
        headers=headers
    )

    response.raise_for_status()

    data = response.json()

    status = data["status"]

    print("Status:", status)

    if status == "completed":
        print("\nTexto transcrito:")
        print(data["text"])
        break

    elif status == "error":
        print("Erro na transcrição:")
        print(data.get("error"))
        break
