import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels
    class_name: str
    confidence: float
    frame_id: int


class Detector:
    def __init__(
        self,
        model_path: str | Path = "yolo26n.pt",
        confidence: float = 0.5,
    ) -> None:
        self._confidence = confidence
        self._model = YOLO(str(model_path))
        logger.info(
            "Loaded detector: model=%s confidence=%.2f",
            model_path,
            confidence,
        )

    def detect(self, frame: np.ndarray, frame_id: int) -> list[Detection]:
        results = self._model(frame, conf=self._confidence, verbose=False)
        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            confs = boxes.conf.cpu().numpy()
            for (x1, y1, x2, y2), cls_id, conf in zip(xyxy, cls_ids, confs):
                detections.append(
                    Detection(
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        class_name=result.names[cls_id],
                        confidence=float(conf),
                        frame_id=frame_id,
                    )
                )
        return detections
