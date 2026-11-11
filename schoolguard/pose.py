"""Детектор людей и поз: YOLO11-Pose в формате ONNX (onnxruntime, DirectML/CPU). Без PyTorch.

Выход для кадра: массив (N, 56): x1, y1, x2, y2, conf, затем 17 x (x, y, conf) в пикселях исходного кадра.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

STRIDE = 32


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    order = scores.argsort()[::-1]
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        r = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[r, 0]); yy1 = np.maximum(boxes[i, 1], boxes[r, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[r, 2]); yy2 = np.minimum(boxes[i, 3], boxes[r, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (area[i] + area[r] - inter + 1e-9)
        order = r[iou <= iou_thr]
    return keep


class PoseDetector:
    def __init__(self, model_path: str | Path, imgsz: int = 640, conf: float = 0.10, iou: float = 0.65,
                 max_det: int = 12, device: str = "auto"):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.log_severity_level = 3
        avail = ort.get_available_providers()
        providers = ["CPUExecutionProvider"]
        if device in ("auto", "gpu") and "DmlExecutionProvider" in avail:
            so.enable_mem_pattern = False
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        try:
            self.sess = ort.InferenceSession(str(model_path), so, providers=providers)
        except Exception:                       # видеокарта не подошла — тихо уходим на процессор
            self.sess = ort.InferenceSession(str(model_path), ort.SessionOptions(), providers=["CPUExecutionProvider"])
        self.device = "GPU" if self.sess.get_providers()[0].startswith("Dml") else "CPU"
        self.inp = self.sess.get_inputs()[0].name
        self.imgsz, self.conf, self.iou, self.max_det = imgsz, conf, iou, max_det

    def _prep(self, frame):
        h, w = frame.shape[:2]
        r = self.imgsz / max(h, w)
        nw, nh = int(round(w * r)), int(round(h * r))
        pw, ph = (-nw) % STRIDE, (-nh) % STRIDE
        img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR) if r != 1 else frame
        left, top = pw // 2, ph // 2
        img = cv2.copyMakeBorder(img, top, ph - top, left, pw - left, cv2.BORDER_CONSTANT, value=(114, 114, 114))
        return img, r, left, top

    def detect_batch(self, frames: list) -> list[np.ndarray]:
        """Кадры одного размера (BGR) -> список массивов (N, 56)."""
        prep = [self._prep(f) for f in frames]
        x = np.stack([p[0] for p in prep])[..., ::-1].transpose(0, 3, 1, 2)
        x = np.ascontiguousarray(x, dtype=np.float32) / 255.0
        out = self.sess.run(None, {self.inp: x})[0]            # (B, 56, A)
        res = []
        for o, (_, r, left, top), f in zip(out, prep, frames):
            o = o.T
            o = o[o[:, 4] >= self.conf]
            if not len(o):
                res.append(np.zeros((0, 56), np.float32)); continue
            b = np.empty((len(o), 4), np.float32)
            b[:, 0] = o[:, 0] - o[:, 2] / 2; b[:, 1] = o[:, 1] - o[:, 3] / 2
            b[:, 2] = o[:, 0] + o[:, 2] / 2; b[:, 3] = o[:, 1] + o[:, 3] / 2
            keep = _nms(b, o[:, 4], self.iou)[: self.max_det]
            d = np.concatenate([b[keep], o[keep, 4:]], 1)
            d[:, [0, 2]] = (d[:, [0, 2]] - left) / r
            d[:, [1, 3]] = (d[:, [1, 3]] - top) / r
            d[:, 5::3] = (d[:, 5::3] - left) / r
            d[:, 6::3] = (d[:, 6::3] - top) / r
            h, w = f.shape[:2]
            d[:, [0, 2]] = d[:, [0, 2]].clip(0, w); d[:, [1, 3]] = d[:, [1, 3]].clip(0, h)
            res.append(d.astype(np.float32))
        return res

    def detect(self, frame) -> np.ndarray:
        return self.detect_batch([frame])[0]


def motion_energy(prev_gray, gray, dets: np.ndarray, scale: float):
    """Энергия движения по межкадровой разности (серые кадры шириной ~320).

    -> (общая по кадру, по каждому боксу); значения 0..1. scale = ширина серого кадра / ширина исходного.
    """
    if prev_gray is None or prev_gray.shape != gray.shape:
        return 0.0, np.zeros(len(dets), np.float32)
    diff = cv2.absdiff(gray, prev_gray).astype(np.float32) / 255.0
    g = float(diff.mean())
    out = np.zeros(len(dets), np.float32)
    H, W = diff.shape
    for i, d in enumerate(dets):
        x1, y1, x2, y2 = (d[:4] * scale).astype(int)
        x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            out[i] = float(diff[y1:y2, x1:x2].mean())
    return g, out


def small_gray(frame, width: int = 320):
    h, w = frame.shape[:2]
    g = cv2.cvtColor(cv2.resize(frame, (width, max(2, int(h * width / w))), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(g, (5, 5), 0), width / w
