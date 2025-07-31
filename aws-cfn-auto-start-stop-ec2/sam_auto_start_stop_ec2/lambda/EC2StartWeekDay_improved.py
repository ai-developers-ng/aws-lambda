"""
Enhanced EC2 Start WeekDay Lambda Function

This function starts EC2 instances based on the 'StartWeekDay' tag during weekdays.
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
    Lambda handler for starting EC2 instances on weekdays based on time tags
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Standardized response with operation results
    """
    logger = configure_logging()
    
    try:
        logger.info("Starting EC2StartWeekDay function")
        logger.info(f"Event: {json.dumps(event, default=str)}")
        
        # Initialize managers
        ec2_manager = EC2Manager()
        timezone_manager = TimezoneManager(logger)
        
        # Set timezone
        timezone = timezone_manager.set_timezone()
        
        # Get current time and validate it's a weekday
        current_time = datetime.datetime.now()
        weekday = current_time.isoweekday()  # Monday is 1, Sunday is 7
        
        logger.info(f"Current time: {current_time}, Weekday: {weekday}, Timezone: {timezone}")
        
        # Check if it's a weekday (Monday to Friday)
        if not (1 <= weekday <= 5):
            logger.info(f"Not a weekday (current: {weekday}), skipping execution")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='start_weekday',
                additional_info={
                    'message': f'Not a weekday (current day: {weekday})',
                    'current_time': current_time.isoformat(),
                    'timezone': timezone,
                    'weekday': weekday
                }
            )
        
        # Get instances with StartWeekDay tag that match current time
        logger.info("Searching for instances with matching StartWeekDay schedule")
        matching_instances = ec2_manager.get_instances_by_time_tag(
            tag_name='StartWeekDay',
            current_time=current_time,
            time_window_minutes=5,
            weekday_filter=(1, 5)  # Monday to Friday
        )
        
        logger.info(f"Found {len(matching_instances)} instances with matching StartWeekDay schedule")
        
        if not matching_instances:
            logger.info("No instances found with matching StartWeekDay schedule")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='start_weekday',
                additional_info={
                    'message': 'No instances found with matching StartWeekDay schedule',
                    'current_time': current_time.isoformat(),
                    'timezone': timezone,
                    'weekday': weekday,
                    'search_criteria': {
                        'tag_name': 'StartWeekDay',
                        'time_window_minutes': 5,
                        'weekday_filter': [1, 5]
                    }
                }
            )
        
        # Filter instances that are in stopped state
        stopped_instances = [
            instance for instance in matching_instances 
            if instance.state == 'stopped'
        ]
        
        # Log instance details
        for instance in matching_instances:
            scheduled_time = instance.tags.get('StartWeekDay', 'N/A')
            logger.info(
                f"Instance {instance.instance_id}: "
                f"scheduled={scheduled_time}, state={instance.state}, "
                f"type={instance.instance_type}, az={instance.availability_zone}"
            )
        
        logger.info(f"Instances in stopped state: {len(stopped_instances)}")
        
        if not stopped_instances:
            logger.info("No instances in stopped state found")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='start_weekday',
                additional_info={
                    'message': 'No instances in stopped state found',
                    'instances_with_schedule': len(matching_instances),
                    'instances_in_stopped_state': 0,
                    'current_time': current_time.isoformat(),
                    'timezone': timezone
                }
            )
        
        # Start the stopped instances
        logger.info(f"Attempting to start {len(stopped_instances)} instances")
        results = ec2_manager.start_instances(stopped_instances)
        
        # Log results summary
        successful_starts = [r for r in results if r.success]
        failed_starts = [r for r in results if not r.success]
        
        logger.info(f"Start operation completed: {len(successful_starts)} successful, {len(failed_starts)} failed")
        
        # Log successful starts
        for result in successful_starts:
            instance = next(i for i in stopped_instances if i.instance_id == result.instance_id)
            scheduled_time = instance.tags.get('StartWeekDay', 'N/A')
            logger.info(f"Successfully started instance: {result.instance_id} (scheduled: {scheduled_time})")
        
        # Log failed starts with details
        for result in failed_starts:
            logger.error(
                f"Failed to start instance {result.instance_id}: "
                f"{result.message} (Error code: {result.error_code})"
            )
        
        # Determine response status code
        status_code = 200 if successful_starts else 207  # 207 for partial success
        if not successful_starts and failed_starts:
            status_code = 500  # All failed
        
        # Create response
        response = create_lambda_response(
            status_code=status_code,
            results=results,
            action='start_weekday',
            additional_info={
                'function_name': 'EC2StartWeekDay',
                'current_time': current_time.isoformat(),
                'timezone': timezone,
                'weekday': weekday,
                'instances_with_schedule': len(matching_instances),
                'instances_in_stopped_state': len(stopped_instances),
                'search_criteria': {
                    'tag_name': 'StartWeekDay',
                    'time_window_minutes': 5,
                    'weekday_filter': [1, 5]
                }
            }
        )
        
        logger.info(f"Function completed successfully. Response status: {status_code}")
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error in EC2StartWeekDay: {str(e)}", exc_info=True)
        
        # Create error response
        error_response = create_lambda_response(
            status_code=500,
            results=[],
            action='start_weekday',
            additional_info={
                'error': 'Internal function error',
                'error_details': str(e),
                'function_name': 'EC2StartWeekDay'
            }
        )
        
        return error_response


# For testing purposes
if __name__ == "__main__":
    # Test event
    test_event = {}
    test_context = type('Context', (), {
        'function_name': 'EC2StartWeekDay',
        'function_version': '$LATEST',
        'invoked_function_arn': 'arn:aws:lambda:us-east-1:123456789012:function:EC2StartWeekDay',
        'memory_limit_in_mb': '256',
        'remaining_time_in_millis': lambda: 30000,
        'log_group_name': '/aws/lambda/EC2StartWeekDay',
        'log_stream_name': '2024/01/01/[$LATEST]test',
        'aws_request_id': 'test-request-id'
    })()
    
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2, default=str))
