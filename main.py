import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import json
import base64
import cv2
import numpy as np
import mediapipe as mp

app = FastAPI(title="AI Proctor - Phase 0")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Initialize MediaPipe Face Detection ---
mp_face_detection = mp.solutions.face_detection
# model_selection=0 is best for short-range (webcam) faces
face_detection = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)

@app.get("/")
async def serve_index():
    return FileResponse("index.html")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    risk_score = 0  
    
    try:
        while True:
            data = await ws.receive_text()
            try:
                payload = json.loads(data)
                event_type = payload.get("event")

                if event_type == "tab_switch":
                    risk_score = min(100, risk_score + 25)
                    msg = "WARNING: Tab switch detected!"
                elif event_type == "window_blur":
                    risk_score = min(100, risk_score + 10)
                    msg = "WARNING: Window lost focus!"
                elif event_type == "connected":
                    msg = "Monitoring started."
                
                # --- NEW: Vision Pipeline ---
                elif event_type == "frame":
                    image_data = payload.get("image", "")
                    if "," in image_data:
                        base64_str = image_data.split(",")[1]
                        img_bytes = base64.b64decode(base64_str)
                        np_arr = np.frombuffer(img_bytes, np.uint8)
                        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                        
                        # MediaPipe requires RGB format, OpenCV uses BGR
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        results = face_detection.process(img_rgb)
                        
                        face_count = 0
                        bounding_boxes = []
                        
                        # If faces are found, extract their coordinates
                        if results.detections:
                            face_count = len(results.detections)
                            for detection in results.detections:
                                bbox = detection.location_data.relative_bounding_box
                                bounding_boxes.append({
                                    "xmin": bbox.xmin,
                                    "ymin": bbox.ymin,
                                    "width": bbox.width,
                                    "height": bbox.height
                                })
                        
                        # Apply Vision Rules
                        msg = "Normal behavior."
                        if face_count == 0:
                            risk_score = min(100, risk_score + 10)
                            msg = "WARNING: Candidate not found!"
                        elif face_count > 1:
                            risk_score = min(100, risk_score + 25)
                            msg = f"WARNING: {face_count} faces detected!"
                        elif risk_score > 0:
                            # Gentle decay: If they are behaving, reduce score slightly
                            risk_score = max(0, risk_score - 1) 

                        # Send the score AND the coordinates back to the UI
                        response = {
                            "status": "connected",
                            "risk_score": risk_score,
                            "message": msg,
                            "vision_data": bounding_boxes, # Only sending coordinates!
                            "type": "vision_update"
                        }
                        await ws.send_text(json.dumps(response))
                    continue 
                else:
                    msg = "Unknown event logged."

                # Send response for non-frame events
                response = {
                    "status": "connected",
                    "risk_score": risk_score,
                    "message": msg,
                }
                await ws.send_text(json.dumps(response))
                
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)