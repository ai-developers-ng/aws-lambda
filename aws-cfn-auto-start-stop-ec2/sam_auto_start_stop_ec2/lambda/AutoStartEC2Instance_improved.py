"""
Enhanced Auto Start EC2 Instance Lambda Function

This function automatically starts EC2 instances based on the 'AutoStart' tag.
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
    Lambda handler for auto-starting EC2 instances
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Standardized response with operation results
    """
    logger = configure_logging()
    
    try:
        logger.info("Starting AutoStartEC2Instance function")
        logger.info(f"Event: {json.dumps(event, default=str)}")
        
        # Initialize EC2 manager
        ec2_manager = EC2Manager()
        
        # Define tag values that indicate auto-start should be enabled
        auto_start_values = ['TRUE', 'True', 'true', '1', 'yes', 'Yes', 'YES', 'on', 'On', 'ON']
        
        # Get stopped instances with AutoStart tag
        logger.info("Searching for stopped instances with AutoStart tag")
        stopped_instances = ec2_manager.get_instances_by_tag(
            tag_name='AutoStart',
            tag_values=auto_start_values,
            instance_states=['stopped']
        )
        
        logger.info(f"Found {len(stopped_instances)} stopped instances with AutoStart tag")
        
        if not stopped_instances:
            logger.info("No instances found in stopped state with AutoStart tag")
            return create_lambda_response(
                status_code=200,
                results=[],
                action='auto_start',
                additional_info={
                    'message': 'No instances found in stopped state with AutoStart tag',
                    'search_criteria': {
                        'tag_name': 'AutoStart',
                        'tag_values': auto_start_values,
                        'instance_states': ['stopped']
                    }
                }
            )
        
        # Log instance details for monitoring
        for instance in stopped_instances:
            logger.info(
                f"Instance to start: {instance.instance_id} "
                f"(Type: {instance.instance_type}, AZ: {instance.availability_zone})"
            )
        
        # Start the instances
        logger.info(f"Attempting to start {len(stopped_instances)} instances")
        results = ec2_manager.start_instances(stopped_instances)
        
        # Log results summary
        successful_starts = [r for r in results if r.success]
        failed_starts = [r for r in results if not r.success]
        
        logger.info(f"Start operation completed: {len(successful_starts)} successful, {len(failed_starts)} failed")
        
        # Log successful starts
        for result in successful_starts:
            logger.info(f"Successfully started instance: {result.instance_id}")
        
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
            action='auto_start',
            additional_info={
                'function_name': 'AutoStartEC2Instance',
                'search_criteria': {
                    'tag_name': 'AutoStart',
                    'tag_values': auto_start_values,
                    'instance_states': ['stopped']
                },
                'instances_found': len(stopped_instances)
            }
        )
        
        logger.info(f"Function completed successfully. Response status: {status_code}")
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error in AutoStartEC2Instance: {str(e)}", exc_info=True)
        
        # Create error response
        error_response = create_lambda_response(
            status_code=500,
            results=[],
            action='auto_start',
            additional_info={
                'error': 'Internal function error',
                'error_details': str(e),
                'function_name': 'AutoStartEC2Instance'
            }
        )
        
        return error_response


# For testing purposes
if __name__ == "__main__":
    # Test event
    test_event = {}
    test_context = type('Context', (), {
        'function_name': 'AutoStartEC2Instance',
        'function_version': '$LATEST',
        'invoked_function_arn': 'arn:aws:lambda:us-east-1:123456789012:function:AutoStartEC2Instance',
        'memory_limit_in_mb': '256',
        'remaining_time_in_millis': lambda: 30000,
        'log_group_name': '/aws/lambda/AutoStartEC2Instance',
        'log_stream_name': '2024/01/01/[$LATEST]test',
        'aws_request_id': 'test-request-id'
    })()
    
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2, default=str))
