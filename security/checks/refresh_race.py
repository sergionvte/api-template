"""Carrera en /auth/refresh con DOS peticiones simultáneas (el caso realista: el
cliente legítimo y un atacante con el token robado). Comprueba si la familia de
sesión queda revocada. Uso: LAB_CREDS=... python refresh_race.py 8901 [intentos]"""
import asyncio, json, os, sys
import httpx

PORT = int(sys.argv[1]); N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
BASE = f"http://127.0.0.1:{PORT}"
creds = json.load(open(os.environ["LAB_CREDS"]))
email, pw = "alice@example.com", creds.get("alice@example.com", creds.get("alice@lab.test"))["password"]

async def trial(ac):
    r = await ac.post("/api/v1/auth/login", data={"username": email, "password": pw})
    tok = r.json()["refresh_token"]
    a, b = await asyncio.gather(*(ac.post("/api/v1/auth/refresh", json={"refresh_token": tok}) for _ in range(2)))
    codes = sorted([a.status_code, b.status_code])
    winner = next((x for x in (a, b) if x.status_code == 200), None)
    after = None
    if winner:
        after = (await ac.post("/api/v1/auth/refresh", json={"refresh_token": winner.json()["refresh_token"]})).status_code
    print(f"códigos={codes}  refresh con el token del ganador después -> {after}"
          + ("  (familia NO revocada)" if after == 200 else ""))

async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as ac:
        for _ in range(N):
            await trial(ac)

asyncio.run(main())
