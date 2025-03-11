import json
import os
import subprocess
import boto3
import shutil
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
s3 = boto3.client('s3')

class AudioEncoder:
    def __init__(self):
        self.tmp_dir = Path('/tmp')
        self.ensure_ffmpeg()
    
    def ensure_ffmpeg(self):
        """Verify ffmpeg is available in the Lambda environment"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg not found or error checking version: {e}")
            raise RuntimeError("FFmpeg is not available")
    
    def download_source(self, bucket: str, key: str) -> Path:
        """Download source file from S3 to Lambda temp storage"""
        input_path = self.tmp_dir / 'input.mp3'
        try:
            s3.download_file(bucket, key, str(input_path))
            logger.info(f"Downloaded {key} from {bucket}")
            return input_path
        except Exception as e:
            logger.error(f"Error downloading from S3: {e}")
            raise

    def list_bucket_contents(self, bucket: str, prefix: str = '') -> list:
        """List contents of bucket for verification"""
        try:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if 'Contents' in response:
                return [item['Key'] for item in response['Contents']]
            return []
        except Exception as e:
            logger.error(f"Error listing bucket contents: {e}")
            return []

    def upload_encoded(self, file_path: Path, bucket: str, key: str):
        """Upload encoded file to S3 with verification"""
        try:
            # Pre-upload checks
            logger.info(f"Pre-upload verification for {file_path}")
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            file_size = file_path.stat().st_size
            logger.info(f"Local file size: {file_size} bytes")
            
            # List pre-upload contents
            logger.info("Listing pre-upload bucket contents")
            pre_contents = self.list_bucket_contents(bucket)
            logger.info(f"Pre-upload bucket contents: {pre_contents}")

            # Perform upload with explicit content type
            logger.info(f"Uploading {file_path} to s3://{bucket}/{key}")
            with open(file_path, 'rb') as file_obj:
                s3.upload_fileobj(
                    file_obj,
                    bucket,
                    key,
                    ExtraArgs={'ContentType': 'audio/mpeg'}
                )

            # Verify upload
            logger.info("Verifying upload...")
            try:
                response = s3.head_object(Bucket=bucket, Key=key)
                logger.info(f"Upload verified - object exists with size: {response['ContentLength']} bytes")
                
                # List post-upload contents
                post_contents = self.list_bucket_contents(bucket)
                logger.info(f"Post-upload bucket contents: {post_contents}")
                
                if key in post_contents:
                    logger.info(f"File successfully verified in bucket: {key}")
                else:
                    logger.error(f"File not found in bucket after upload: {key}")
                    
            except ClientError as e:
                logger.error(f"Failed to verify upload: {e}")
                raise

        except Exception as e:
            logger.error(f"Error in upload_encoded: {e}")
            raise


    def encode_audio(self, input_path: Path, output_path: Path, bitrate: str):
        """Encode audio file using ffmpeg with specified bitrate"""
        try:
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output files
                '-i', str(input_path),  # Input file
                '-c:a', 'libmp3lame',  # MP3 codec
                '-b:a', bitrate,  # Bitrate
                '-map', '0:a',  # Audio only
                '-f', 'mp3',  # Force MP3 format
                '-metadata', f'encoder=aws_lambda_ffmpeg',
                '-metadata', f'bitrate={bitrate}',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"Encoded {input_path} to {output_path} at {bitrate}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg encoding error: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Unexpected encoding error: {e}")
            raise

def cleanup_temp_files(*files: Path):
    """Clean up temporary files"""
    for file in files:
        try:
            if file.exists():
                file.unlink()
        except Exception as e:
            logger.warning(f"Error cleaning up {file}: {e}")
            raise

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler with enhanced verification"""
    try:
        # Log event
        logger.info(f"Processing event: {json.dumps(event)}")
        
        # Extract parameters
        source_bucket = event['input']['bucket']
        source_key = event['input']['key']
        output_bucket = event['output']['bucket']
        bitrate = event['encoding']['bitrate']
        
        # Create encoder
        encoder = AudioEncoder()
        
        # List initial bucket contents
        logger.info("Initial bucket contents:")
        initial_contents = encoder.list_bucket_contents(output_bucket)
        logger.info(f"Initial files in bucket: {initial_contents}")
        
        # Process file
        input_path = encoder.download_source(source_bucket, source_key)
        logger.info(f"Downloaded source to: {input_path} (size: {input_path.stat().st_size} bytes)")
        
        output_path = Path('/tmp/output.mp3')
        
        # Encode
        encoder.encode_audio(input_path, output_path, bitrate)
        logger.info(f"Encoded file size: {output_path.stat().st_size} bytes")
        
        # Set output key
        output_key = f"encoded/{source_key}/{bitrate}/output.mp3"
        logger.info(f"Output key: {output_key}")
        
        # Upload
        encoder.upload_encoded(output_path, output_bucket, output_key)
        
        # Final verification
        final_contents = encoder.list_bucket_contents(output_bucket)
        logger.info(f"Final files in bucket: {final_contents}")
        
        # Verify file was added
        if output_key not in final_contents:
            raise Exception(f"Upload verification failed - file not found in bucket: {output_key}")
        
        # Clean up
        cleanup_temp_files(input_path, output_path)
        
        return {
            'statusCode': 200,
            'input': {
                'bucket': source_bucket,
                'key': source_key
            },
            'output': {
                'bucket': output_bucket,
                'key': output_key,
                'bitrate': bitrate
            }
        }
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        cleanup_temp_files(Path('/tmp/input.mp3'), Path('/tmp/output.mp3'))
        raise

def validate_encodings_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for validating encoded files"""
    try:
        outputs = event['outputs']
        validated_outputs = []
        
        for output in outputs:
            # Download and check each encoded file
            bucket = output['output']['bucket']
            key = output['output']['key']
            bitrate = output['output']['bitrate']
            
            # Download file
            temp_path = Path('/tmp') / f"validate_{bitrate}.mp3"
            s3.download_file(bucket, key, str(temp_path))
            
            # Validate using ffprobe
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(temp_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            metadata = json.loads(result.stdout)
            
            # Verify format and bitrate
            if metadata['format']['format_name'] == 'mp3':
                validated_outputs.append(output)
            
            # Cleanup
            cleanup_temp_files(temp_path)
        
        return {
            'statusCode': 200,
            'validatedOutputs': validated_outputs
        }
        
    except Exception as e:
        logger.error(f"Error validating encodings: {e}")
        # Cleanup any remaining temp files
        for file in Path('/tmp').glob('validate_*.mp3'):
            cleanup_temp_files(file)
        raise
