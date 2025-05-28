import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
from fuzzywuzzy import fuzz
from yt_dlp import YoutubeDL
import re
import logging
from textblob import TextBlob
import time

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.cookies_path = os.path.join(base_dir, 'cookies.txt')
        
        # Initialize cookies file only if it doesn't exist
        if not os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, 'w') as f:
                    f.write("# HTTP Cookie File\n")
            except Exception as e:
                logger.warning(f"Could not create cookies file: {str(e)}")

    def sanitize_filename(self, filename):
        filename = filename.split('?')[0]
        filename = re.sub(r'[#@$%^&*!(){}[\];:"\'<>,?/\\|~`]', '', filename)
        filename = re.sub(r'\s+', '_', filename.strip())
        filename = os.path.splitext(filename)[0]
        return filename

    def download_video(self, url, session_id):
        output_folder = os.path.join(self.base_dir, 'downloads', session_id)
        os.makedirs(output_folder, exist_ok=True)

        # Basic options that work for most videos
        ydl_opts = {
            'quiet': False,
            'outtmpl': os.path.join(output_folder, '%(id)s.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'retries': 3,
            'socket_timeout': 30,
            'extract_flat': False,
            'ignoreerrors': False,
            'no_warnings': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
        }

        # Only add cookies if the file exists and is not empty
        if os.path.exists(self.cookies_path) and os.path.getsize(self.cookies_path) > 50:  # 50 bytes minimum
            ydl_opts['cookiefile'] = self.cookies_path
        else:
            logger.warning("No valid cookies file found, proceeding without cookies")

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_filename = ydl.prepare_filename(info)

                file_ext = os.path.splitext(downloaded_filename)[1].lower()
                clean_base = self.sanitize_filename(info.get('title', 'video'))
                final_filename = f"{info['id']}_{clean_base}{file_ext}"
                final_path = os.path.join(output_folder, final_filename)

                if downloaded_filename != final_path:
                    os.rename(downloaded_filename, final_path)

                return final_path
        except Exception as e:
            error_msg = str(e)
            if "Sign in to confirm you're not a bot" in error_msg:
                error_msg += ("\n\nTo download restricted videos, please provide YouTube cookies. "
                            "You can export cookies from your browser using extensions like "
                            "'Get cookies.txt' for Chrome or 'Export Cookies' for Firefox.")
            logger.error(f"Error downloading video: {error_msg}", exc_info=True)
            raise RuntimeError(f"Failed to download video: {error_msg}")

    # [Rest of your existing methods remain unchanged...]
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