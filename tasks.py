from celery import shared_task
from textblob import TextBlob
import os
import uuid
import logging
from backend.video_processor import download_video, process_video

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_video_task(self, url=None, file_path=None, session_id=None):
    try:
        if not session_id:
            session_id = str(uuid.uuid4())[:8]

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={
                'progress': 5,
                'message': "Initializing processing",
                'status': 'Processing...'
            }
        )

        # Setup directories
        BASE_DIR = os.path.dirname(os.path.dirname(__file__))
        static_dir = os.path.join(BASE_DIR, 'static')
        download_dir = os.path.join(static_dir, 'downloads', session_id)
        frame_dir = os.path.join(static_dir, 'frames', session_id)
        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(frame_dir, exist_ok=True)

        # Download or use uploaded video
        if url:
            self.update_state(
                state='PROGRESS',
                meta={'progress': 20, 'message': "Downloading video"}
            )
            video_path = download_video(url, output_folder=download_dir)
            if not video_path:
                raise ValueError("Failed to download video")
        elif file_path:
            self.update_state(
                state='PROGRESS',
                meta={'progress': 20, 'message': "Using uploaded video"}
            )
            video_path = file_path
        else:
            raise ValueError("Either URL or file_path must be provided")

        # Process video
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': "Processing video frames"}
        )
        results = process_video(video_path, output_dir=frame_dir)

        # Process results
        processed_results = []
        for i, (path, text) in enumerate(results):
            filename = os.path.basename(path)
            spelled_text = str(TextBlob(text).correct())
            processed_results.append({
                'frame_path': f"/static/frames/{session_id}/{filename}",
                'text': spelled_text
            })

            # Update progress
            progress = 70 + int((i / len(results)) * 25)
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': progress,
                    'message': f"Processing frame {i+1}/{len(results)}"
                }
            )

        return {
            'status': 'SUCCESS',
            'progress': 100,
            'session_id': session_id,
            'results': processed_results,
            'video_path': f"/static/downloads/{session_id}/{os.path.basename(video_path)}" if url 
                         else f"/static/uploads/{session_id}/{os.path.basename(file_path)}",
            'message': 'Processing complete'
        }

    except Exception as e:
        logger.error(f"Error in video processing: {str(e)}", exc_info=True)
        return {
            'status': 'FAILURE',
            'progress': 100,
            'error': str(e),
            'message': 'Processing failed'
        }