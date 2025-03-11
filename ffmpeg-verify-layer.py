import json
import subprocess
import os

def lambda_handler(event, context):
    try:
        ffmpeg_path = '/opt/bin/ffmpeg'
        ffprobe_path = '/opt/bin/ffprobe'
        
        if not os.path.exists(ffmpeg_path):
            raise Exception(f"FFmpeg not found at {ffmpeg_path}")
        if not os.path.exists(ffprobe_path):
            raise Exception(f"FFprobe not found at {ffprobe_path}")
        
        ffmpeg_version = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True
        )
        
        ffprobe_version = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            text=True
        )
        
        return {
            'statusCode': 200,
            'body': {
                'message': 'FFmpeg layer test successful',
                'ffmpeg_version': ffmpeg_version.stdout.split('\n')[0],
                'ffprobe_version': ffprobe_version.stdout.split('\n')[0],
                'ffmpeg_path': ffmpeg_path,
                'ffprobe_path': ffprobe_path
            }
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': {
                'message': 'FFmpeg layer test failed',
                'error': str(e)
            }
        }
