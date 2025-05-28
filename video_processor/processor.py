import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
from fuzzywuzzy import fuzz
from pytube import YouTube
import re
import logging
from textblob import TextBlob
import time
import json

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, base_dir):
        self.base_dir = base_dir

    def sanitize_filename(self, filename):
        filename = filename.split('?')[0]
        filename = re.sub(r'[#@$%^&*!(){}\[\];:"\'<>,?/\\|~`]', '', filename)
        filename = re.sub(r'\s+', '_', filename.strip())
        filename = os.path.splitext(filename)[0]
        return filename

    def download_video(self, url, session_id):
        output_folder = os.path.join(self.base_dir, 'downloads', session_id)
        os.makedirs(output_folder, exist_ok=True)

        try:
            yt = YouTube(url)
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            if not stream:
                raise RuntimeError("No suitable stream found")

            clean_title = self.sanitize_filename(yt.title)
            final_filename = f"{yt.video_id}_{clean_title}.mp4"
            final_path = os.path.join(output_folder, final_filename)
            stream.download(output_path=output_folder, filename=final_filename)
            return final_path

        except Exception as e:
            logger.error(f"Failed to download video using pytube: {str(e)}")
            raise RuntimeError(f"Failed to download video: {str(e)}")

    def is_black_or_white(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = np.mean(gray)
        return mean < 10 or mean > 245

    def is_blurry(self, frame, threshold=100.0):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        return lap_var < threshold

    def extract_text(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        pil_img = Image.fromarray(gray)
        text = pytesseract.image_to_string(pil_img)
        return text.strip()

    def process_video(self, video_path, session_id):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Could not open video file")

        frame_dir = os.path.join(self.base_dir, 'frames', session_id)
        os.makedirs(frame_dir, exist_ok=True)

        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_index = 0
        clusters = []
        current_cluster = []
        current_text = ""

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_index % 5 != 0:
                frame_index += 1
                continue

            resized = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)

            if self.is_black_or_white(resized) or self.is_blurry(resized):
                frame_index += 1
                continue

            text = self.extract_text(resized).lower()
            if not text:
                frame_index += 1
                continue

            if current_cluster and fuzz.token_set_ratio(current_text, text) < 70:
                best_frame = max(current_cluster, key=lambda x: len(x[2]))
                clusters.append(best_frame)
                current_cluster = []

            current_text = text
            current_cluster.append((resized.copy(), frame_index, text))
            frame_index += 1

        if current_cluster:
            best_frame = max(current_cluster, key=lambda x: len(x[2]))
            clusters.append(best_frame)

        saved = []
        results_file = os.path.join(frame_dir, "results.txt")
        with open(results_file, 'w') as f:
            for idx, (frame, index, text) in enumerate(clusters):
                filename = f"frame_{index:04d}.png"
                path = os.path.join(frame_dir, filename)
                cv2.imwrite(path, frame)
                spelled_text = str(TextBlob(text).correct())
                saved.append({
                    'frame_path': f"/frames/{session_id}/{filename}",
                    'text': spelled_text
                })
                f.write(f"{filename}: {text}\n")

        cap.release()
        return saved
