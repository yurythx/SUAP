#!/usr/bin/env python3
"""Run NAT commands on PVE via termproxy websocket (API token with Sys.Console)."""
import asyncio
import json
import os
import ssl
import urllib.parse
import urllib.request

HOST = os.environ.get("PVE_HOST", "192.168.29.51")
TOKEN = os.environ["PVE_API_TOKEN"]
USER = os.environ.get("PVE_API_USER", TOKEN.split("=", 1)[0])
LOGIN_PASSWORDS = [item for item in os.environ.get("PVE_LOGIN_PASSWORDS", "").split(",") if item]

COMMANDS = r"""
set -x
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -C POSTROUTING -s 192.168.110.0/24 -o vmbr0 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 192.168.110.0/24 -o vmbr0 -j MASQUERADE
iptables -C FORWARD -i vmbr1 -j ACCEPT 2>/dev/null || iptables -I FORWARD -i vmbr1 -j ACCEPT
iptables -C FORWARD -o vmbr1 -j ACCEPT 2>/dev/null || iptables -I FORWARD -o vmbr1 -j ACCEPT
sysctl -w net.ipv4.ip_forward=1
echo NAT_MARKER_OK
cat /proc/sys/net/ipv4/ip_forward
iptables -t nat -S POSTROUTING
iptables -S FORWARD | head -30
"""


def api_post(path: str, data: dict | None = None) -> dict:
    body = None
    headers = {"Authorization": f"PVEAPIToken={TOKEN}"}
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(
        f"https://{HOST}:8006/api2/json{path}",
        data=body,
        method="POST",
        headers=headers,
    )
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


async def main() -> None:
    import websockets

    data = api_post("/nodes/pve/termproxy")["data"]
    port = data["port"]
    ticket = data["ticket"]
    user = data.get("user") or USER
    print("termproxy port=", port)

    qs = urllib.parse.urlencode({"port": port, "vncticket": ticket})
    uri = f"wss://{HOST}:8006/api2/json/nodes/pve/vncwebsocket?{qs}"
    ctx = ssl._create_unverified_context()
    headers = {"Authorization": f"PVEAPIToken={TOKEN}"}

    async with websockets.connect(
        uri, ssl=ctx, max_size=8_000_000, additional_headers=headers
    ) as ws:
        await ws.send(f"{user}:{ticket}\n")
        first = await asyncio.wait_for(ws.recv(), timeout=10)
        print("auth_reply=", repr(first)[:200])

        async def send_text(s: str) -> None:
            await ws.send(b"0" + s.encode())

        async def read_for(seconds: float) -> str:
            out = []
            end = asyncio.get_event_loop().time() + seconds
            while asyncio.get_event_loop().time() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if isinstance(msg, bytes):
                    out.append(msg[1:].decode("utf-8", errors="replace") if msg[:1] == b"0" else msg.decode("utf-8", errors="replace"))
                else:
                    out.append(msg)
            return "".join(out)

        buf = await read_for(2)
        print("banner=", repr(buf)[:300])

        if "login:" in buf.lower():
            await send_text("root\n")
            buf2 = await read_for(2)
            print("after_user=", repr(buf2)[:200])
            for pw in LOGIN_PASSWORDS:
                await send_text(pw + "\n")
                buf3 = await read_for(3)
                print("after_pw=", repr(buf3)[:300])
                if "Login incorrect" in buf3 or "login:" in buf3.lower():
                    continue
                if "#" in buf3 or "$" in buf3 or "root@" in buf3:
                    break

        await send_text("bash -lc " + json.dumps(COMMANDS) + "\n")
        text = await read_for(12)
        print("---OUTPUT---")
        print(text)
        if "NAT_MARKER_OK" not in text:
            raise SystemExit("NAT commands did not confirm")


if __name__ == "__main__":
    asyncio.run(main())
