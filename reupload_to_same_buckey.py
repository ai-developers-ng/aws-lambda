import boto3
import time
import os
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Define the file count threshold
FILE_COUNT_THRESHOLD = 200

def lambda_handler(event, context):
    """
    If a bucket has less than 200 files, it re-uploads them with a 5-sec delay
    and sends an SNS alert with the list of re-uploaded files. Otherwise, it
    sends an alert that the threshold was exceeded.

    :param event: AWS Lambda uses this parameter to pass in event data.
    :param context: AWS Lambda uses this parameter to provide runtime information.
    """
    # Get environment variables
    bucket_name = os.environ.get('S3_BUCKET_NAME')
    sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')

    # Validate environment variables
    if not bucket_name or not sns_topic_arn:
        logger.error("S3_BUCKET_NAME and/or SNS_TOPIC_ARN environment variables not set.")
        return {
            'statusCode': 500,
            'body': 'S3_BUCKET_NAME and/or SNS_TOPIC_ARN environment variables not set.'
        }

    s3_client = boto3.client('s3')
    sns_client = boto3.client('sns')

    try:
        # Get the list of all files in the bucket
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)
        
        files_to_process = []
        for page in pages:
            if 'Contents' in page:
                files_to_process.extend(page['Contents'])
        
        file_count = len(files_to_process)
        logger.info(f"Found {file_count} files in bucket: {bucket_name}")

        # --- Check if the file count is below the threshold ---
        if file_count >= FILE_COUNT_THRESHOLD:
            message = (f"Processing for S3 bucket '{bucket_name}' was skipped. "
                       f"The bucket contains {file_count} files, which meets or exceeds the "
                       f"threshold of {FILE_COUNT_THRESHOLD}.")
            subject = f"SKIPPED: File Re-upload for S3 Bucket: {bucket_name}"
            
            logger.warning(message)
            sns_client.publish(TopicArn=sns_topic_arn, Message=message, Subject=subject)
            
            return {
                'statusCode': 200,
                'body': message
            }

        # --- Proceed with re-upload if below threshold ---
        if not files_to_process:
            logger.info(f"No files found in bucket: {bucket_name}")
            return {
                'statusCode': 200,
                'body': f'No files found in bucket: {bucket_name}'
            }
            
        reuploaded_files = []
        for file in files_to_process:
            file_key = file['Key']
            logger.info(f"Processing file: {file_key}")

            copy_source = {'Bucket': bucket_name, 'Key': file_key}
            s3_client.copy_object(
                Bucket=bucket_name,
                Key=file_key,
                CopySource=copy_source,
                MetadataDirective='COPY'
            )

            logger.info(f"Successfully re-uploaded: {file_key}")
            reuploaded_files.append(file_key)
            time.sleep(5)

        # Send SNS alert with the list of re-uploaded files
        if reuploaded_files:
            message_body = "The following files were successfully re-uploaded to the S3 bucket '{}':\n\n{}".format(
                bucket_name,
                "\n".join(reuploaded_files)
            )
            sns_subject = f"SUCCESS: File Re-upload Report for S3 Bucket: {bucket_name}"

            logger.info("Sending success SNS notification.")
            sns_client.publish(TopicArn=sns_topic_arn, Message=message_body, Subject=sns_subject)

        return {
            'statusCode': 200,
            'body': f'Successfully re-uploaded {len(reuploaded_files)} files to bucket: {bucket_name}'
        }

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        try:
            sns_client.publish(
                TopicArn=sns_topic_arn,
                Message=f"An error occurred during the S3 file re-upload process for bucket {bucket_name}.\n\nError: {e}",
                Subject=f"FAILURE: S3 File Re-upload for Bucket: {bucket_name}"
            )
        except Exception as sns_error:
            logger.error(f"Failed to send failure SNS notification: {sns_error}")
        return {
            'statusCode': 500,
            'body': f'An error occurred: {e}'
        }
