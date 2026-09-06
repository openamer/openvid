"""OPENVID Voice — speech in/out for the WebUI + Desktop.

Server endpoints (added to server.py):
    POST /stt  {audio: base64 wav/webm} -> {text}   (OpenAI Whisper API or
                                                     local faster-whisper)
    GET  /tts?text=...                  -> audio/mpeg (OpenAI TTS; graceful
                                                     error if no key)
Client (webui) captures mic via MediaRecorder, sends to /stt, plays /tts.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request


def stt_openai(audio_b64: str, api_key: str, model: str = "whisper-1") -> dict:
    raw = base64.b64decode(audio_b64)
    boundary = "----openvidvoice"
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio.webm"\r\n'
            f"Content-Type: audio/webm\r\n\r\n").encode() + raw + \
           f"\r\n--{boundary}\r\n" \
           f'Content-Disposition: form-data; name="model"\r\n\r\n{model}\r\n' \
           f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return {"ok": True, "text": json.loads(r.read())["text"]}


def tts_openai(text: str, api_key: str, voice: str = "alloy") -> bytes:
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps({"model": "tts-1", "input": text[:4000], "voice": voice}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()
