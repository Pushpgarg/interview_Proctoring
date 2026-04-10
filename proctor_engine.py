import mediapipe as mp
from vision_analyzer import VisionAnalyzer
from risk_assessor import RiskAssessor


class ProctorEngine:
    def __init__(self):
        # Face Detection for crowd/no-face checks (runs ~1/sec)
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.5
        )

        # FaceMesh for reading, talking, head pose (runs every frame at 12 FPS)
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            min_detection_confidence=0.5,
            refine_landmarks=True,  # Required for iris landmarks 468-477
        )

        self.vision = VisionAnalyzer()
        self.risk = RiskAssessor()

        # Frame counter for scheduling heavy face detection
        self.frame_counter = 0
        self.last_face_count = 1
        self.last_bounding_boxes = []

    def process_frame(self, img_rgb, time_scale, is_in_background):
        self.frame_counter += 1

        # --- Run face detection every 12th frame (~1/sec at 12 FPS) ---
        # This handles crowd detection and no-face detection
        if self.frame_counter % 12 == 0:
            results_detection = self.face_detection.process(img_rgb)
            if results_detection.detections:
                self.last_face_count = len(results_detection.detections)
                self.last_bounding_boxes = results_detection.detections
            else:
                self.last_face_count = 0
                self.last_bounding_boxes = []

        face_count = self.last_face_count

        vision_data = []
        vision_type = "none"
        event_code = "normal"

        if face_count == 0:
            self.risk.risk_score = min(
                100.0, self.risk.risk_score + (self.risk.PENALTY_NO_FACE * time_scale)
            )
            msg = "WARNING: Candidate not found!"
            event_code = "no_face"

        elif face_count == 1:
            # --- FaceMesh runs EVERY frame (12 FPS) ---
            # All detections (reading, talking, head pose) extracted from this single run
            mesh_results = self.face_mesh.process(img_rgb)

            if mesh_results.multi_face_landmarks:
                landmarks = mesh_results.multi_face_landmarks[0].landmark

                # Extract ALL behavioral signals from the same landmark set
                states = self.vision.analyze(landmarks)
                score, msg, event_code = self.risk.calculate(
                    states, is_in_background, time_scale
                )

                # Send landmark data for AI vision overlay
                for landmark in landmarks:
                    vision_data.append({"x": landmark.x, "y": landmark.y})
            else:
                # FaceMesh couldn't find a face even though detection said 1
                msg = "Normal behavior."

            vision_type = "mesh"

        elif face_count > 1:
            self.risk.risk_score = min(
                100.0, self.risk.risk_score + (self.risk.PENALTY_CROWD * time_scale)
            )
            msg = f"WARNING: {face_count} faces detected!"
            event_code = "crowd"

            for detection in self.last_bounding_boxes:
                bbox = detection.location_data.relative_bounding_box
                vision_data.append(
                    {
                        "xmin": bbox.xmin,
                        "ymin": bbox.ymin,
                        "width": bbox.width,
                        "height": bbox.height,
                    }
                )
            vision_type = "boxes"

        return self.risk.risk_score, msg, vision_data, vision_type, event_code