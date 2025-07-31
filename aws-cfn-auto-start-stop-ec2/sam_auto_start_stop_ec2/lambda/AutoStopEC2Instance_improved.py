"""
Enhanced Auto Stop EC2 Instance Lambda Function

This function automatically stops EC2 instances based on the 'AutoStop' tag.
Enhanced with comprehensive error handling, monitoring, and production-ready features.

Author: Enhanced by BlackBoxAI
Version: 2.0.0
Python: 3.11+
"""

import json
from typing import Dict, Any
from ec2_utils_improved import (
    EC2Manager,
    TagValidator,
    create_lambda_response,
    configure_logging
)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for auto-stopping EC2 instances
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Standardized response with operation results
    """
    logger = configure_logging()
    
    try:
        logger.info("Starting AutoStopEC2Instance function")
        logger.info(f"Event: {json.dumps(event, default=str)}")
        
        # Initialize EC2 manager
        ec2_manager = EC2Manager()
        
        # Define tag values that indicate auto-stop should be enabled
        auto_stop_values = ['TRUE', 'True', 'true', '1', 'yes', 'Yes', 'YES', 'on', 'On', 'ON']
        
        # Get running instances with AutoStop tag
        logger.info("Searching for running instances with AutoStop tag")
        running_instances = ec2_manager.get_instances_by_tag(
            tag_name='AutoStop',
            tag_values=auto_stop_values,
            instance_states=['running']
        )
        
        logger.info(f"Found {len(running_instances)} running instances with AutoStop tag")
        
        if not running_instances:
            logger.info("No instances found in running state with AutoStop tag")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='auto_stop',
                additional_info={
                    'message': 'No instances found in running state with AutoStop tag',
                    'search_criteria': {
                        'tag_name': 'AutoStop',
                        'tag_values': auto_stop_values,
                        'instance_states': ['running']
                    }
                }
            )
        
        # Log instance details for monitoring
        for instance in running_instances:
            logger.info(
                f"Instance to stop: {instance.instance_id} "
                f"(Type: {instance.instance_type}, AZ: {instance.availability_zone})"
            )
        
        # Stop the instances
        logger.info(f"Attempting to stop {len(running_instances)} instances")
        results = ec2_manager.stop_instances(running_instances)
        
        # Log results summary
        successful_stops = [r for r in results if r.success]
        failed_stops = [r for r in results if not r.success]
        
        logger.info(f"Stop operation completed: {len(successful_stops)} successful, {len(failed_stops)} failed")
        
        # Log successful stops
        for result in successful_stops:
            logger.info(f"Successfully stopped instance: {result.instance_id}")
        
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
            action='auto_stop',
            additional_info={
                'function_name': 'AutoStopEC2Instance',
                'search_criteria': {
                    'tag_name': 'AutoStop',
                    'tag_values': auto_stop_values,
                    'instance_states': ['running']
                },
                'instances_found': len(running_instances)
            }
        )
        
        logger.info(f"Function completed successfully. Response status: {status_code}")
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error in AutoStopEC2Instance: {str(e)}", exc_info=True)
        
        # Create error response
        error_response = create_lambda_response(
            status_code=500,
            results=[],
            action='auto_stop',
            additional_info={
                'error': 'Internal function error',
                'error_details': str(e),
                'function_name': 'AutoStopEC2Instance'
            }
        )
        
        return error_response


# For testing purposes
if __name__ == "__main__":
    # Test event
    test_event = {}
    test_context = type('Context', (), {
        'function_name': 'AutoStopEC2Instance',
        'function_version': '$LATEST',
        'invoked_function_arn': 'arn:aws:lambda:us-east-1:123456789012:function:AutoStopEC2Instance',
        'memory_limit_in_mb': '256',
        'remaining_time_in_millis': lambda: 30000,
        'log_group_name': '/aws/lambda/AutoStopEC2Instance',
        'log_stream_name': '2024/01/01/[$LATEST]test',
        'aws_request_id': 'test-request-id'
    })()
    
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2, default=str))
