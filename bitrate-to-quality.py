import json

BITRATE_TO_QUALITY = {
    "64k": "low",
    "128k": "medium",
    "192k": "high"
}

def lambda_handler(event, context):
    bitrate = event.get("output", {}).get("bitrate")
    event["quality"] = BITRATE_TO_QUALITY.get(bitrate, "unknown")
    return event

