import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import supervision as sv
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# ── Class name normalisation ──────────────────────────────────────────────────
# The Roboflow construction-safety dataset uses mixed-case / spaced names.
# Normalise to the lowercase canonical names the rules engine expects.
_NAME_NORMALISE: dict[str, str] = {
    # PPE present
    "hardhat":          "hardhat",
    "Hardhat":          "hardhat",
    "safety vest":      "vest",
    "Safety Vest":      "vest",
    "vest":             "vest",
    "gloves":           "gloves",
    "Gloves":           "gloves",
    "safety shoes":     "safety_shoes",
    "Safety Shoes":     "safety_shoes",
    "mask":             "mask",
    "Mask":             "mask",
    # PPE absent (explicit "no-PPE" classes from the dataset)
    "no-hardhat":       "no-hardhat",
    "NO-Hardhat":       "no-hardhat",
    "no-safety vest":   "no-vest",
    "NO-Safety Vest":   "no-vest",
    "no-mask":          "no-mask",
    "NO-Mask":          "no-mask",
    # Persons
    "person":           "person",
    "Person":           "person",
    "worker":           "person",
    "Worker":           "person",
    # Vehicles / equipment (keep lowercase)
    "excavators":       "excavator",
    "EXCAVATORS":       "excavator",
    "dump truck":       "dump_truck",
    "wheel loader":     "wheel_loader",
}


def _normalise(raw: str) -> str:
    return _NAME_NORMALISE.get(raw, raw.lower())


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels
    class_name: str
    confidence: float
    frame_id: int


class Detector:
    def __init__(
        self,
        model_path: str | Path = "yolo26s.pt",
        confidence: float = 0.25,
        imgsz: int = 640,
        sahi: bool = False,
        sahi_slice_wh: int = 640,
        sahi_overlap_wh: int = 100,
    ) -> None:
        self._confidence = confidence
        self._imgsz = imgsz
        self._model = YOLO(str(model_path))
        self._names: dict[int, str] = self._model.names
        self._slicer = (
            sv.InferenceSlicer(
                callback=self._infer_sv,
                slice_wh=sahi_slice_wh,
                overlap_wh=sahi_overlap_wh,
            )
            if sahi
            else None
        )
        logger.info(
            "Loaded detector: model=%s confidence=%.2f imgsz=%d sahi=%s",
            model_path,
            confidence,
            imgsz,
            sahi,
        )

    def _infer_sv(self, frame: np.ndarray) -> sv.Detections:
        """Run YOLO on a single tile; used as the SAHI callback."""
        results = self._model(frame, conf=self._confidence, imgsz=self._imgsz, verbose=False)
        all_xyxy, all_confs, all_cls_ids = [], [], []
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            all_xyxy.append(boxes.xyxy.cpu().numpy())
            all_confs.append(boxes.conf.cpu().numpy())
            all_cls_ids.append(boxes.cls.cpu().numpy().astype(int))
        if not all_xyxy:
            return sv.Detections.empty()
        return sv.Detections(
            xyxy=np.concatenate(all_xyxy),
            confidence=np.concatenate(all_confs),
            class_id=np.concatenate(all_cls_ids),
        )

    def _sv_to_detections(self, sv_dets: sv.Detections, frame_id: int) -> list[Detection]:
        if sv_dets is None or len(sv_dets) == 0:
            return []
        detections: list[Detection] = []
        for i in range(len(sv_dets)):
            x1, y1, x2, y2 = sv_dets.xyxy[i]
            cls_id = int(sv_dets.class_id[i])
            conf = float(sv_dets.confidence[i]) if sv_dets.confidence is not None else 0.0
            detections.append(
                Detection(
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    class_name=_normalise(self._names.get(cls_id, str(cls_id))),
                    confidence=conf,
                    frame_id=frame_id,
                )
            )
        return detections

    def detect(self, frame: np.ndarray, frame_id: int) -> list[Detection]:
        if self._slicer is not None:
            return self._sv_to_detections(self._slicer(frame), frame_id)

        results = self._model(frame, conf=self._confidence, imgsz=self._imgsz, verbose=False)
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
                        class_name=_normalise(self._names[cls_id]),
                        confidence=float(conf),
                        frame_id=frame_id,
                    )
                )
        return detections
