import boto3
import time
import os
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lists all files in an S3 bucket and re-uploads them to the same bucket
    with a 5-second delay between each upload.

    :param event: AWS Lambda uses this parameter to pass in event data.
    :param context: AWS Lambda uses this parameter to provide runtime information.
    """
    # Get the S3 bucket name from the environment variables
    bucket_name = os.environ.get('S3_BUCKET_NAME')

    if not bucket_name:
        logger.error("S3_BUCKET_NAME environment variable not set.")
        return {
            'statusCode': 500,
            'body': 'S3_BUCKET_NAME environment variable not set.'
        }

    s3_client = boto3.client('s3')

    try:
        # Get the list of all files in the bucket
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        files = response.get('Contents', [])

        if not files:
            logger.info(f"No files found in bucket: {bucket_name}")
            return {
                'statusCode': 200,
                'body': f'No files found in bucket: {bucket_name}'
            }

        logger.info(f"Found {len(files)} files in bucket: {bucket_name}")

        # Re-upload each file with a 5-second delay
        for file in files:
            file_key = file['Key']
            logger.info(f"Re-uploading file: {file_key}")

            # Define the copy source
            copy_source = {
                'Bucket': bucket_name,
                'Key': file_key
            }

            # Copy the object to itself to trigger a re-upload
            s3_client.copy_object(
                Bucket=bucket_name,
                Key=file_key,
                CopySource=copy_source
            )

            logger.info(f"Successfully re-uploaded: {file_key}")

            # Wait for 5 seconds before the next upload
            time.sleep(5)

        return {
            'statusCode': 200,
            'body': f'Successfully re-uploaded {len(files)} files to bucket: {bucket_name}'
        }

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return {
            'statusCode': 500,
            'body': f'An error occurred: {e}'
        }
