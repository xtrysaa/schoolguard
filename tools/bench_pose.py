"""Скорость ONNX-детектора и сверка с Ultralytics (PyTorch)."""
import glob
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schoolguard.pose import PoseDetector
from schoolguard.tracker import ByteTracker

f = sorted(glob.glob("data/raw/surv/fight/*"))[0]
cap = cv2.VideoCapture(f); frames = []
while len(frames) < 32:
    ok, fr = cap.read()
    if not ok:
        break
    frames.append(fr)
print(f, frames[0].shape, len(frames))
for name in ["yolo11s-pose", "yolo11n-pose"]:
    for dev in ["gpu", "cpu"]:
        d = PoseDetector(f"models/onnx/{name}.onnx", device=dev)
        d.detect(frames[0]); d.detect_batch(frames[:8])
        t = time.time(); [d.detect(x) for x in frames]; a = (time.time() - t) / len(frames)
        t = time.time(); [d.detect_batch(frames[i:i + 8]) for i in range(0, len(frames), 8)]; b = (time.time() - t) / len(frames)
        print(name, dev, d.device, f"single {a * 1000:.1f} ms  batch8 {b * 1000:.1f} ms/frame", len(d.detect(frames[0])))
if "--parity" in sys.argv:
    from ultralytics import YOLO
    m = YOLO("yolo11s-pose.pt"); r = m.predict(frames[10], imgsz=640, conf=0.25, verbose=False)[0]
    d = PoseDetector("models/onnx/yolo11s-pose.onnx"); o = d.detect(frames[10]); o = o[o[:, 4] >= 0.25]
    print("ultra", np.round(r.boxes.xyxy.cpu().numpy()[:3]), np.round(r.boxes.conf.cpu().numpy()[:3], 3))
    print("onnx ", np.round(o[:3, :4]), np.round(o[:3, 4], 3))
    tr = ByteTracker()
    for i, fr in enumerate(frames):
        ps = tr.update(d.detect(fr), i / 25)
    print([(p.id, round(p.conf, 2)) for p in ps])
