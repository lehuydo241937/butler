import requests
import base64
import os

def test_audio_api():
    url = "http://localhost:8000/audio"
    # Create a dummy wav file
    dummy_audio = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x11\x2b\x00\x00\x11\x2b\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
    
    files = {'file': ('test.wav', dummy_audio, 'audio/wav')}
    
    print(f"Testing {url}...")
    try:
        response = requests.post(url, files=files)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Success!")
            print(f"Transcription: {data.get('transcription')}")
            print(f"Reply: {data.get('reply')}")
            print(f"Audio received: {'Yes' if data.get('audio_base64') else 'No'}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}. (Is the API running?)")

if __name__ == "__main__":
    test_audio_api()
