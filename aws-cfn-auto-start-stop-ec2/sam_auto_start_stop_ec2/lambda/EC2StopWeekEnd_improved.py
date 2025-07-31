"""
Enhanced EC2 Stop WeekEnd Lambda Function

This function stops EC2 instances based on the 'StopWeekEnd' tag during weekends.
Enhanced with comprehensive error handling, monitoring, and production-ready features.

Author: Enhanced by BlackBoxAI
Version: 2.0.0
Python: 3.11+
"""

import json
import datetime
from typing import Dict, Any
from ec2_utils_improved import (
    EC2Manager,
    TimezoneManager,
    TagValidator,
    create_lambda_response,
    configure_logging
)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for stopping EC2 instances on weekends based on time tags
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Standardized response with operation results
    """
    logger = configure_logging()
    
    try:
        logger.info("Starting EC2StopWeekEnd function")
        logger.info(f"Event: {json.dumps(event, default=str)}")
        
        # Initialize managers
        ec2_manager = EC2Manager()
        timezone_manager = TimezoneManager(logger)
        
        # Set timezone
        timezone = timezone_manager.set_timezone()
        
        # Get current time and validate it's a weekend
        current_time = datetime.datetime.now()
        weekday = current_time.isoweekday()  # Monday is 1, Sunday is 7
        
        logger.info(f"Current time: {current_time}, Weekday: {weekday}, Timezone: {timezone}")
        
        # Check if it's a weekend (Saturday to Sunday)
        if not (6 <= weekday <= 7):
            logger.info(f"Not a weekend (current: {weekday}), skipping execution")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='stop_weekend',
                additional_info={
                    'message': f'Not a weekend (current day: {weekday})',
                    'current_time': current_time.isoformat(),
                    'timezone': timezone,
                    'weekday': weekday
                }
            )
        
        # Get instances with StopWeekEnd tag that match current time
        logger.info("Searching for instances with matching StopWeekEnd schedule")
        matching_instances = ec2_manager.get_instances_by_time_tag(
            tag_name='StopWeekEnd',
            current_time=current_time,
            time_window_minutes=5,
            weekday_filter=(6, 7)  # Saturday to Sunday
        )
        
        logger.info(f"Found {len(matching_instances)} instances with matching StopWeekEnd schedule")
        
        if not matching_instances:
            logger.info("No instances found with matching StopWeekEnd schedule")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='stop_weekend',
                additional_info={
                    'message': 'No instances found with matching StopWeekEnd schedule',
                    'current_time': current_time.isoformat(),
                    'timezone': timezone,
                    'weekday': weekday,
                    'search_criteria': {
                        'tag_name': 'StopWeekEnd',
                        'time_window_minutes': 5,
                        'weekday_filter': [6, 7]
                    }
                }
            )
        
        # Filter instances that are in running state
        running_instances = [
            instance for instance in matching_instances 
            if instance.state == 'running'
        ]
        
        # Log instance details
        for instance in matching_instances:
            scheduled_time = instance.tags.get('StopWeekEnd', 'N/A')
            logger.info(
                f"Instance {instance.instance_id}: "
                f"scheduled={scheduled_time}, state={instance.state}, "
                f"type={instance.instance_type}, az={instance.availability_zone}"
            )
        
        logger.info(f"Instances in running state: {len(running_instances)}")
        
        if not running_instances:
            logger.info("No instances in running state found")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='stop_weekend',
                additional_info={
                    'message': 'No instances in running state found',
                    'instances_with_schedule': len(matching_instances),
                    'instances_in_running_state': 0,
                    'current_time': current_time.isoformat(),
                    'timezone': timezone
                }
            )
        
        # Stop the running instances
        logger.info(f"Attempting to stop {len(running_instances)} instances")
        results = ec2_manager.stop_instances(running_instances)
        
        # Log results summary
        successful_stops = [r for r in results if r.success]
        failed_stops = [r for r in results if not r.success]
        
        logger.info(f"Stop operation completed: {len(successful_stops)} successful, {len(failed_stops)} failed")
        
        # Log successful stops
        for result in successful_stops:
            instance = next(i for i in running_instances if i.instance_id == result.instance_id)
            scheduled_time = instance.tags.get('StopWeekEnd', 'N/A')
            logger.info(f"Successfully stopped instance: {result.instance_id} (scheduled: {scheduled_time})")
        
        # Log failed stops with details
        for result in failed_stops:
            logger.error(
                f"Failed to stop instance {result.instance_id}: "
                f"{result.message} (Error code: {result.error_code})"
            )
        
        # Determine response status code
        status_code = 200 if successful_stops else 207  # 207 for partial success
        if not successful_stops and failed_stops:
            status_code = 500  # All failed
        
        # Create response
        response = create_lambda_response(
            status_code=status_code,
            results=results,
            action='stop_weekend',
            additional_info={
                'function_name': 'EC2StopWeekEnd',
                'current_time': current_time.isoformat(),
                'timezone': timezone,
                'weekday': weekday,
                'instances_with_schedule': len(matching_instances),
                'instances_in_running_state': len(running_instances),
                'search_criteria': {
                    'tag_name': 'StopWeekEnd',
                    'time_window_minutes': 5,
                    'weekday_filter': [6, 7]
                }
            }
        )
        
        logger.info(f"Function completed successfully. Response status: {status_code}")
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error in EC2StopWeekEnd: {str(e)}", exc_info=True)
        
        # Create error response
        error_response = create_lambda_response(
            status_code=500,
            results=[],
            action='stop_weekend',
            additional_info={
                'error': 'Internal function error',
                'error_details': str(e),
                'function_name': 'EC2StopWeekEnd'
            }
        )
        
        return error_response


# For testing purposes
if __name__ == "__main__":
    # Test event
    test_event = {}
    test_context = type('Context', (), {
        'function_name': 'EC2StopWeekEnd',
        'function_version': '$LATEST',
        'invoked_function_arn': 'arn:aws:lambda:us-east-1:123456789012:function:EC2StopWeekEnd',
        'memory_limit_in_mb': '256',
        'remaining_time_in_millis': lambda: 30000,
        'log_group_name': '/aws/lambda/EC2StopWeekEnd',
        'log_stream_name': '2024/01/01/[$LATEST]test',
        'aws_request_id': 'test-request-id'
    })()
    
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2, default=str))
