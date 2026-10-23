import asyncio
import json
import urllib.request
import aiohttp
import subprocess
import time
import base64
import os

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9222
USER_DATA_DIR = r"C:\Users\lipsi\AppData\Local\Temp\chrome_lead_test"

cmd = [
    CHROME_PATH,
    f"--remote-debugging-port={PORT}",
    "--headless",
    "--disable-gpu",
    f"--user-data-dir={USER_DATA_DIR}",
    "--window-size=430,932",
    "http://127.0.0.1:8080/"
]

proc = subprocess.Popen(cmd)
time.sleep(2.5)

async def test_ui():
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json")
        tabs = json.loads(req.read().decode())
        ws_url = tabs[0]["webSocketDebuggerUrl"]
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                msg_id = 0
                async def send(method, params=None):
                    nonlocal msg_id
                    msg_id += 1
                    payload = {"id": msg_id, "method": method, "params": params or {}}
                    await ws.send_json(payload)
                    while True:
                        msg = await ws.receive_json()
                        if msg.get("id") == msg_id:
                            return msg.get("result", {})

                await send("Page.enable")
                await send("Runtime.enable")
                
                # Wait 3.5 seconds for app to load and render cards
                await asyncio.sleep(3.5)
                
                # Switch to "new" tab (Парсер) where cards and filters are located
                await send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const newTabBtn = document.querySelector('.rail-btn[data-tab=\"new\"]');
                        if (newTabBtn) newTabBtn.click();
                        return 'Switched to new tab';
                    })()
                    """
                })
                await asyncio.sleep(2.0)
                
                # 1. Check how many cards are rendered
                eval_res = await send("Runtime.evaluate", {"expression": "document.querySelectorAll('.card').length"})
                cards_count = eval_res.get("result", {}).get("value")
                print("Rendered cards count:", cards_count)
                
                # 2. Click on the first card
                click_res = await send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const firstCard = document.querySelector('.card[data-lead]');
                        if (!firstCard) return 'No card found';
                        const leadId = firstCard.dataset.lead;
                        const cardTitle = firstCard.querySelector('.card-name')?.textContent || '';
                        firstCard.click();
                        return { clicked: true, leadId, cardTitle };
                    })()
                    """,
                    "returnByValue": True
                })
                print("Card click result:", click_res.get("result", {}).get("value"))
                
                # Wait 1.5 seconds for drawer animation
                await asyncio.sleep(1.5)
                
                # 3. Check if drawer is open and inspect its contents
                drawer_res = await send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const dr = document.getElementById('drawer');
                        if (!dr) return 'No drawer';
                        const isOpen = dr.classList.contains('open');
                        const title = dr.querySelector('.d-name')?.textContent || '';
                        const sub = dr.querySelector('.d-sub')?.textContent || '';
                        const channels = [...dr.querySelectorAll('.chbtn')].map(b => b.textContent.trim());
                        const draft = dr.querySelector('[data-draft]')?.value || '';
                        return { isOpen, title, sub, channelsCount: channels.length, channels, draftLen: draft.length };
                    })()
                    """,
                    "returnByValue": True
                })
                drawer_data = drawer_res.get("result", {}).get("value")
                print("Drawer state after click:", drawer_data)
                
                # Capture screenshot of open drawer
                shot_dr = await send("Page.captureScreenshot", {"format": "png"})
                with open(r"C:\Users\lipsi\.gemini\antigravity\brain\5c9c1b1d-af84-429e-ba4f-5a7ddb68bc56\miniapp_drawer_open.png", "wb") as f:
                    f.write(base64.b64decode(shot_dr["data"]))
                print("Saved miniapp_drawer_open.png")
                
                # Close drawer
                await send("Runtime.evaluate", {"expression": "closeLead()"})
                await asyncio.sleep(0.8)
                
                # 4. Click on data-pick-city
                city_click_res = await send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const btn = document.querySelector('[data-pick-city]');
                        if (!btn) return 'No city button';
                        btn.click();
                        return 'City button clicked';
                    })()
                    """
                })
                print("City button:", city_click_res.get("result", {}).get("value"))
                await asyncio.sleep(0.8)
                
                # Check pick modal
                pick_res = await send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        const pick = document.getElementById('pick');
                        const isOpen = pick?.classList.contains('open');
                        const title = document.getElementById('pickH')?.textContent || '';
                        const options = [...document.querySelectorAll('#pickO .opt')].map(o => o.textContent.trim());
                        return { isOpen, title, optionsCount: options.length, firstOptions: options.slice(0, 5) };
                    })()
                    """,
                    "returnByValue": True
                })
                pick_data = pick_res.get("result", {}).get("value")
                print("Pick modal state:", pick_data)
                
                # Capture screenshot of beautiful pick modal
                shot_pick = await send("Page.captureScreenshot", {"format": "png"})
                with open(r"C:\Users\lipsi\.gemini\antigravity\brain\5c9c1b1d-af84-429e-ba4f-5a7ddb68bc56\miniapp_pick_modal.png", "wb") as f:
                    f.write(base64.b64decode(shot_pick["data"]))
                print("Saved miniapp_pick_modal.png")
                
    finally:
        proc.terminate()

asyncio.run(test_ui())
