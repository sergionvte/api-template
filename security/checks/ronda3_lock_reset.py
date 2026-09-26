"""Ronda 3: ¿un login del titular desde su IP conocida levanta el bloqueo para todos?"""
import json, os, sys
import httpx
BASE = f"http://127.0.0.1:{sys.argv[1]}"
PW = {e: d["password"] for e, d in json.load(open(os.environ["LAB_CREDS"])).items()}
c = httpx.Client(base_url=BASE, timeout=30)
def login(pw, addr):
    return c.post("/api/v1/auth/login", data={"username": "alice@example.com", "password": pw},
                  headers={"X-Forwarded-For": addr}).status_code
HOME = "198.51.100.20"
print("fallos del atacante:", [login(f"wrong-{i}-xxxxxxxx", f"203.0.113.{120+i}") for i in range(5)])
print("titular desde IP nueva (bloqueada):", login(PW["alice@example.com"], "192.0.2.130"))
print("titular desde IP conocida:", login(PW["alice@example.com"], HOME))
print("atacante tras el login del titular, 5 intentos más:",
      [login(f"again-{i}-xxxxxxxx", f"203.0.113.{140+i}") for i in range(6)])
