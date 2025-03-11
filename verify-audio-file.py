import boto3
import json

s3 = boto3.client("s3")

MAX_FILE_SIZE_MB = 50  # (MB)
VALID_AUDIO_TYPES = {"audio/mp3"}

def lambda_handler(event, context):
    try:
        # Extract bucket name and object key from EventBridge event
        detail = event.get("detail", {})
        bucket_name = detail.get("bucket", {}).get("name")
        object_key = detail.get("object", {}).get("key")
        file_size = detail.get("object", {}).get("size", 0)

        if not bucket_name or not object_key:
            return log_and_respond("Missing bucket or object key in event", 400)

        response = s3.head_object(Bucket=bucket_name, Key=object_key)
        content_type = response.get("ContentType")

        if content_type not in VALID_AUDIO_TYPES:
            return log_and_respond(f"Invalid file type: {content_type}", 400, bucket_name, object_key)

        if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return log_and_respond(f"File too large ({file_size} bytes). Max size is {MAX_FILE_SIZE_MB}MB", 400, bucket_name, object_key)

        # Successful validation
        return log_and_respond("File is valid", 200, bucket_name, object_key)

    except s3.exceptions.ClientError as e:
        return log_and_respond(f"S3 Error: {str(e)}", 500, bucket_name, object_key)

    except Exception as e:
        return log_and_respond(f"Unexpected error: {str(e)}", 500)


def log_and_respond(message, status_code, bucket=None, key=None):
    response = {"bucket": bucket, "file": key, "message": message, "status": status_code}
    print(json.dumps(response))
    return response

