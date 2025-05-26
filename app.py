import os
import uuid
import logging
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from werkzeug.utils import secure_filename
from fpdf import FPDF, XPos, YPos
from PIL import Image
from video_processor.processor import VideoProcessor
import re
# from pdf_generator.generator import PDFGenerator

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173"])

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize processors
video_processor = VideoProcessor(BASE_DIR)
# pdf_generator = PDFGenerator(BASE_DIR)

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ========== Routes ==========

# Upload Video
@app.route('/api/upload/video', methods=['POST'])
def upload_video():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        session_id = str(uuid.uuid4())[:8]
        upload_dir = os.path.join(BASE_DIR, 'uploads', session_id)
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(file.filename)
        video_path = os.path.join(upload_dir, filename)
        file.save(video_path)
        try:
            results = video_processor.process_video(video_path, session_id)
            return jsonify({
                'status': 'SUCCESS',
                'session_id': session_id,
                'results': results,
                'video_path': f"/uploads/{session_id}/{filename}",
                'message': 'Processing complete'
            })
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}", exc_info=True)
            return jsonify({'status': 'FAILURE', 'error': str(e), 'message': 'Processing failed'}), 500
    return jsonify({'error': 'Invalid file type'}), 400

# YouTube Download
@app.route('/api/download/youtube', methods=['POST'])
def download_youtube():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'No YouTube URL provided'}), 400
    try:
        session_id = str(uuid.uuid4())[:8]
        video_path = video_processor.download_video(data['url'], session_id)
        results = video_processor.process_video(video_path, session_id)
        return jsonify({
            'status': 'SUCCESS',
            'session_id': session_id,
            'results': results,
            'video_path': f"/downloads/{session_id}/{os.path.basename(video_path)}",
            'message': 'YouTube video processed successfully'
        })
    except Exception as e:
        logger.error(f"Error processing YouTube video: {str(e)}", exc_info=True)
        return jsonify({'status': 'FAILURE', 'error': str(e), 'message': 'YouTube video processing failed'}), 500

# PDF from text list (with pdf_generator class)
# PDF from frames + results.txt
def extract_frame_number(filename):
    # This pattern tries to extract the number between underscores or before extension
    # Adjust regex according to your actual filename pattern!
    match = re.search(r'_(\d+)\.', filename)
    if match:
        return int(match.group(1))
    else:
        return float('inf') 
@app.route('/api/generate_pdf/<session_id>', methods=['POST'])
def generate_pdf_by_session_id(session_id):
    try:
        data = request.get_json()
        selected_frames = data.get('selected_frames', [])

        frames_dir = os.path.join("frames", session_id)
        if not os.path.exists(frames_dir):
            return jsonify({'error': 'Session not found'}), 404

        all_files = os.listdir(frames_dir)
        frame_files = [f for f in all_files if f.endswith(('.png', '.jpg', '.jpeg'))]
        frame_files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))

        if selected_frames:
            try:
                selected_indices = [int(i) for i in selected_frames]
                frame_files = [frame_files[i] for i in selected_indices]
            except (ValueError, IndexError):
                return jsonify({'error': 'Invalid frame selection'}), 400

        if not frame_files:
            return jsonify({'error': 'No frames available'}), 400

        # Safe read results.txt line by line in binary mode, decode with errors='replace'
        text_mapping = {}
        results_file = os.path.join(frames_dir, "results.txt")
        if os.path.exists(results_file):
            with open(results_file, 'rb') as f:
                for raw_line in f:
                    try:
                        line = raw_line.decode('utf-8')
                    except UnicodeDecodeError:
                        # fallback with replacement char for undecodable bytes
                        line = raw_line.decode('utf-8', errors='replace')
                    if ':' in line:
                        filename, text = line.split(':', 1)
                        text_mapping[filename.strip()] = text.strip()

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        try:
            pdf.add_font('Arial', '', 'c:/windows/fonts/arial.ttf', uni=True)
            pdf.add_font('Arial', 'B', 'c:/windows/fonts/arialbd.ttf', uni=True)
            font_family = 'Arial'
        except Exception:
            font_family = "helvetica"

        line_height = 5
        page_width = 210
        margin = 10
        max_text_width = page_width - 2 * margin

        for frame_file in frame_files:
            pdf.add_page()
            frame_path = os.path.join(frames_dir, frame_file)

            try:
                with Image.open(frame_path) as img:
                    width, height = img.size
                    aspect_ratio = width / height
                    img_width = 180
                    img_height = img_width / aspect_ratio
                    if img_height > 150:
                        img_height = 150
                        img_width = img_height * aspect_ratio
                    x_pos = (page_width - img_width) / 2
                    pdf.image(frame_path, x=x_pos, y=20, w=img_width, h=img_height)
            except Exception as e:
                logger.error(f"Error loading image {frame_file}: {str(e)}")
                continue

            text = text_mapping.get(frame_file, "No text detected")

            # Set font and position for text box
            pdf.set_font(font_family, size=10)
            text_y = 20 + img_height + 10
            pdf.set_y(text_y)

            # Calculate lines with split_only=True (does not output, just splits)
            lines = pdf.multi_cell(max_text_width, line_height, text, split_only=True)
            text_height = len(lines) * line_height

            # Draw background rectangle behind the multiline text
            pdf.set_fill_color(240, 240, 240)
            pdf.rect(margin, text_y, max_text_width, text_height, 'F')

            # Now output the actual multiline text on top of the rectangle
            pdf.set_y(text_y)
            pdf.multi_cell(0, line_height, text)

        pdf_dir = os.path.join("pdfs", session_id)
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, "frames_report.pdf")
        pdf.output(pdf_path)

        return send_from_directory(pdf_dir, "frames_report.pdf", as_attachment=True)

    except Exception as e:
        logger.error(f"PDF generation error: {str(e)}", exc_info=True)
        return jsonify({'error': f"Failed to generate PDF: {str(e)}"}), 500


# File Serving Routes
@app.route('/uploads/<session_id>/<filename>')
def serve_upload(session_id, filename):
    return serve_file('uploads', session_id, filename)

@app.route('/downloads/<session_id>/<filename>')
def serve_download(session_id, filename):
    return serve_file('downloads', session_id, filename)

@app.route('/frames/<session_id>/<filename>')
def serve_frame(session_id, filename):
    return serve_file('frames', session_id, filename)

@app.route('/pdfs/<session_id>/<filename>')
def serve_pdf(session_id, filename):
    return serve_file('pdfs', session_id, filename)

def serve_file(folder, session_id, filename):
    valid_folders = ['frames', 'downloads', 'uploads', 'pdfs']
    if folder not in valid_folders:
        return jsonify({'error': 'Invalid folder'}), 404
    directory = os.path.join(BASE_DIR, folder, session_id)
    try:
        return send_from_directory(directory, filename)
    except FileNotFoundError:
        logger.error(f"File not found: {os.path.join(directory, filename)}")
        return jsonify({'error': 'File not found'}), 404

# Startup
if __name__ == '__main__':
    for folder in ['downloads', 'frames', 'uploads', 'pdfs']:
        os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
