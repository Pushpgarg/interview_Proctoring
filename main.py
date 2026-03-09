import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import json

app = FastAPI(title="AI Proctor - Phase 0")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_index():
    return FileResponse("index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    risk_score = 0  # Initialize candidate's risk score
    
    try:
        while True:
            data = await ws.receive_text()
            
            try:
                # Parse the incoming JSON from JavaScript
                payload = json.loads(data)
                event_type = payload.get("event")

                # The Risk Scoring Engine
                if event_type == "tab_switch":
                    risk_score = min(100, risk_score + 25) # Add 25 points, max 100
                    msg = "WARNING: Tab switch detected!"
                elif event_type == "window_blur":
                    risk_score = min(100, risk_score + 10) # Add 10 points
                    msg = "WARNING: Window lost focus!"
                elif event_type == "connected":
                    msg = "Monitoring started."
                else:
                    msg = f"Unknown event logged."

                # Send the updated score and message back to the UI
                response = {
                    "status": "connected",
                    "risk_score": risk_score,
                    "message": msg,
                }
                
            except json.JSONDecodeError:
                # Fallback just in case standard text is sent
                response = {
                    "status": "connected",
                    "risk_score": risk_score,
                    "message": f"Echo: {data}",
                }

            await ws.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        print("Client disconnected")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
