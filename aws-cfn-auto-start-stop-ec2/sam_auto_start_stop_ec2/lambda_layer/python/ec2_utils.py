import boto3
import logging
import os
import time
import datetime

def configure_logging():
    """Configures logging for the Lambda function."""
    logger = logging.getLogger()
    for handler in logger.handlers:
        logger.removeHandler(handler)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())
    return logger

def get_ec2_client():
    """Returns a boto3 EC2 client."""
    return boto3.client('ec2')

def get_instances_by_tag(ec2_client, tag_name, tag_values, instance_states):
    """
    Retrieves EC2 instances based on tags and instance states.

    Args:
        ec2_client: The boto3 EC2 client.
        tag_name: The name of the tag to filter by (e.g., 'AutoStart').
        tag_values: A list of tag values to match (e.g., ['TRUE', 'True', 'true']).
        instance_states: A list of instance states to filter by (e.g., ['stopped']).

    Returns:
        A list of instance IDs.
    """
    filters = [
        {
            'Name': f'tag:{tag_name}',
            'Values': tag_values
        },
        {
            'Name': 'instance-state-name',
            'Values': instance_states
        }
    ]
    try:
        response = ec2_client.describe_instances(Filters=filters)
        instance_ids = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_ids.append(instance['InstanceId'])
        return instance_ids
    except Exception as e:
        logging.error(f"Error describing instances: {e}")
        raise

def start_ec2_instances(ec2_client, instance_ids):
    """Starts a list of EC2 instances."""
    if not instance_ids:
        logging.info("No instances to start.")
        return
    try:
        response = ec2_client.start_instances(InstanceIds=instance_ids)
        logging.info(f"Successfully initiated start for instances: {instance_ids}")
        return response
    except Exception as e:
        logging.error(f"Error starting instances {instance_ids}: {e}")
        raise

def stop_ec2_instances(ec2_client, instance_ids):
    """Stops a list of EC2 instances."""
    if not instance_ids:
        logging.info("No instances to stop.")
        return
    try:
        response = ec2_client.stop_instances(InstanceIds=instance_ids)
        logging.info(f"Successfully initiated stop for instances: {instance_ids}")
        return response
    except Exception as e:
        logging.error(f"Error stopping instances {instance_ids}: {e}")
        raise

def set_region_timezone():
    """Sets the timezone based on REGION_TZ environment variable."""
    logger = logging.getLogger()
    
    time_now = datetime.datetime.now()
    logger.info(f"Current time before timezone setting: {time_now}")
    
    try:
        timezone_var = os.environ.get('REGION_TZ')
        if timezone_var:
            logger.info(f"Using REGION_TZ environment variable: {timezone_var}")
        else:
            timezone_var = os.environ.get('TZ', 'UTC')
            logger.info(f"REGION_TZ not available, using TZ or defaulting to UTC: {timezone_var}")
    except Exception as e:
        logger.warning(f"Error getting timezone environment variable: {e}")
        timezone_var = 'UTC'
    
    timezone = timezone_var if timezone_var else 'UTC'
    logger.info(f"Setting timezone to: {timezone}")
    
    os.environ['TZ'] = str(timezone)
    time.tzset()
    
    time_after = datetime.datetime.now()
    logger.info(f"Current time after timezone setting: {time_after}")
    
    return timezone

def get_instances_by_time_tag(ec2_client, tag_name, current_time, time_window_minutes=5, weekday_filter=None):
    """
    Retrieves EC2 instances based on time-based tags and current time.
    
    Args:
        ec2_client: The boto3 EC2 client.
        tag_name: The name of the time tag to filter by (e.g., 'StartWeekDay').
        current_time: Current datetime object.
        time_window_minutes: Time window in minutes for matching (default: 5).
        weekday_filter: Tuple of (min_weekday, max_weekday) for filtering (e.g., (1, 5) for Mon-Fri).
    
    Returns:
        A list of dictionaries with instance_id and scheduled_time.
    """
    logger = logging.getLogger()
    
    try:
        response = ec2_client.describe_instances()
        matching_instances = []
        
        time_plus = current_time + datetime.timedelta(minutes=time_window_minutes)
        time_minus = current_time - datetime.timedelta(minutes=time_window_minutes)
        current_time_str = current_time.strftime('%H:%M')
        max_time_str = time_plus.strftime('%H:%M')
        min_time_str = time_minus.strftime('%H:%M')
        current_weekday = current_time.isoweekday()  # Monday is 1, Sunday is 7
        
        logger.info(f"Current time: {current_time_str}, Time window: {min_time_str} - {max_time_str}, Weekday: {current_weekday}")
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                if 'Tags' in instance:
                    for tag in instance['Tags']:
                        if tag['Key'] == tag_name:
                            scheduled_time = tag['Value']
                            
                            # Check if time matches within window
                            time_matches = min_time_str <= scheduled_time <= max_time_str
                            
                            # Check weekday filter if provided
                            weekday_matches = True
                            if weekday_filter:
                                min_day, max_day = weekday_filter
                                weekday_matches = min_day <= current_weekday <= max_day
                            
                            if time_matches and weekday_matches:
                                matching_instances.append({
                                    'instance_id': instance['InstanceId'],
                                    'scheduled_time': scheduled_time,
                                    'current_state': instance['State']['Name']
                                })
                                logger.info(f"Found matching instance {instance['InstanceId']} with scheduled time {scheduled_time}")
                            break
        
        return matching_instances
        
    except Exception as e:
        logger.error(f"Error getting instances by time tag: {e}")
        raise

def process_time_based_instances(ec2_client, instances_data, target_state, action):
    """
    Processes instances based on time scheduling.
    
    Args:
        ec2_client: The boto3 EC2 client.
        instances_data: List of instance dictionaries from get_instances_by_time_tag.
        target_state: The required current state for action (e.g., 'stopped' for start action).
        action: 'start' or 'stop'.
    
    Returns:
        Number of instances processed.
    """
    logger = logging.getLogger()
    processed_count = 0
    
    for instance_data in instances_data:
        instance_id = instance_data['instance_id']
        current_state = instance_data['current_state']
        scheduled_time = instance_data['scheduled_time']
        
        if current_state == target_state:
            try:
                if action == 'start':
                    ec2_client.start_instances(InstanceIds=[instance_id])
                    logger.info(f"Started instance {instance_id} scheduled for {scheduled_time}")
                elif action == 'stop':
                    ec2_client.stop_instances(InstanceIds=[instance_id])
                    logger.info(f"Stopped instance {instance_id} scheduled for {scheduled_time}")
                processed_count += 1
            except Exception as e:
                logger.error(f"Error {action}ing instance {instance_id}: {e}")
        else:
            logger.info(f"Instance {instance_id} not in {target_state} state (current: {current_state})")
    
    return processed_count
