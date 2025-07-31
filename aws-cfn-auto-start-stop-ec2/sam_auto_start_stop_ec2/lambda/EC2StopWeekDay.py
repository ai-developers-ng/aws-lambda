import datetime
from ec2_utils import (
    configure_logging, 
    get_ec2_client, 
    set_region_timezone, 
    get_instances_by_time_tag, 
    process_time_based_instances
)

def lambda_handler(event, context):
    logger = configure_logging()
    
    try:
        # Set timezone
        timezone = set_region_timezone()
        
        # Get current time
        current_time = datetime.datetime.now()
        weekday = current_time.isoweekday()  # Monday is 1, Sunday is 7
        
        logger.info(f"Current time: {current_time}, Weekday: {weekday}, Timezone: {timezone}")
        
        # Get EC2 client
        ec2_client = get_ec2_client()
        
        # Get instances with StopWeekDay tag that match current time (weekdays only)
        matching_instances = get_instances_by_time_tag(
            ec2_client=ec2_client,
            tag_name='StopWeekDay',
            current_time=current_time,
            time_window_minutes=5,
            weekday_filter=(1, 5)  # Monday to Friday
        )
        
        logger.info(f"Found {len(matching_instances)} instances with matching StopWeekDay schedule")
        
        if matching_instances:
            # Process instances that are in 'running' state
            processed_count = process_time_based_instances(
                ec2_client=ec2_client,
                instances_data=matching_instances,
                target_state='running',
                action='stop'
            )
            
            logger.info(f"Successfully processed {processed_count} instances for stop")
        else:
            logger.info("No instances found with matching StopWeekDay schedule")
        
        return {
            'statusCode': 200,
            'body': f'Processed {len(matching_instances)} instances with StopWeekDay schedule'
        }
        
    except Exception as e:
        logger.error(f"Error in EC2StopWeekDay: {str(e)}")
        raise
