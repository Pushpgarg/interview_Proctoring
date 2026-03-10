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

# --- Initialize MediaPipe Models ---
# 1. Bounding Box Detector (Fast, counts people)
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.5)

# 2. FaceMesh Detector (Heavy, extracts 468 points)
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, min_detection_confidence=0.5)

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
                
                # --- Vision Pipeline ---
                elif event_type == "frame":
                    image_data = payload.get("image", "")
                    if "," in image_data:
                        base64_str = image_data.split(",")[1]
                        img_bytes = base64.b64decode(base64_str)
                        np_arr = np.frombuffer(img_bytes, np.uint8)
                        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                        
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        
                        # Step 1: Always run fast face detection to count people
                        results_detection = face_detection.process(img_rgb)
                        face_count = 0
                        bounding_boxes = []
                        
                        if results_detection.detections:
                            face_count = len(results_detection.detections)
                            for detection in results_detection.detections:
                                bbox = detection.location_data.relative_bounding_box
                                bounding_boxes.append({
                                    "xmin": bbox.xmin, "ymin": bbox.ymin,
                                    "width": bbox.width, "height": bbox.height
                                })
                        
                        # Apply Vision Rules & Determine Hybrid UI Payload
                        # Apply Vision Rules & Determine Hybrid UI Payload
                        msg = "Normal behavior."
                        vision_data = []
                        vision_type = "none"

                        if face_count == 0:
                            risk_score = min(100, risk_score + 10)
                            msg = "WARNING: Candidate not found!"
                            
                        elif face_count > 1:
                            # Crowd detected! Fall back to bounding boxes
                            risk_score = min(100, risk_score + 25)
                            msg = f"WARNING: {face_count} faces detected!"
                            vision_data = bounding_boxes
                            vision_type = "boxes"

                        elif face_count == 1:
                            # --- THE FIX: Candidate is alone. Reduce the risk score! ---
                            if risk_score > 0:
                                risk_score = max(0, risk_score - 1)
                                
                            # Run deep FaceMesh analysis
                            mesh_results = face_mesh.process(img_rgb)
                            if mesh_results.multi_face_landmarks:
                                for landmark in mesh_results.multi_face_landmarks[0].landmark:
                                    vision_data.append({"x": landmark.x, "y": landmark.y})
                            vision_type = "mesh"
                            
                        elif face_count > 1:
                            # Step 3: Crowd detected! Fall back to bounding boxes
                            risk_score = min(100, risk_score + 25)
                            msg = f"WARNING: {face_count} faces detected!"
                            vision_data = bounding_boxes
                            vision_type = "boxes"
                            
                        elif risk_score > 0:
                            risk_score = max(0, risk_score - 1) 

                        response = {
                            "status": "connected",
                            "risk_score": risk_score,
                            "message": msg,
                            "vision_data": vision_data,
                            "vision_type": vision_type, # Tell frontend what to draw
                            "type": "vision_update"
                        }
                        await ws.send_text(json.dumps(response))
                    continue 
                else:
                    msg = "Unknown event logged."

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
    