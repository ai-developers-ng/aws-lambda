"""
Improved RDS Stop WeekEnd Lambda Function

This function stops RDS instances and clusters on weekends based on the 'StopWeekEnd' tag.
Enhanced with better error handling, logging, timezone management, and code structure.

Author: Improved by AI Assistant
Version: 2.0.0
"""

import json
import logging
from typing import Dict, Any, List
from rds_utils import RDSManager, TagProcessor, TimeZoneManager, create_lambda_response


def setup_logging() -> logging.Logger:
    """Set up structured logging for the Lambda function."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove default handler to avoid duplicate logs
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add custom handler with structured format
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for stopping RDS resources on weekends based on schedule.
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Standardized response dictionary
    """
    logger = setup_logging()
    logger.info("Starting RDS Stop WeekEnd function")
    
    try:
        # Initialize managers
        rds_manager = RDSManager()
        tag_processor = TagProcessor()
        tz_manager = TimeZoneManager()
        
        # Set timezone
        timezone = tz_manager.set_timezone()
        logger.info(f"Operating in timezone: {timezone}")
        
        # Check if today is a weekend
        if not tz_manager.is_weekend():
            message = "Today is not a weekend, skipping execution"
            logger.info(message)
            return create_lambda_response(True, message, {'is_weekend': False})
        
        # Get all RDS resources
        instances, clusters = rds_manager.get_all_rds_resources()
        all_resources = instances + clusters
        
        if not all_resources:
            message = "No RDS resources found in the region"
            logger.info(message)
            return create_lambda_response(True, message)
        
        # Get all read replicas to exclude them from operations
        all_read_replicas = rds_manager.get_all_read_replicas(all_resources)
        logger.info(f"Found {len(all_read_replicas)} read replicas to exclude")
        
        # Process each resource
        stopped_resources = []
        skipped_resources = []
        error_resources = []
        
        for resource in all_resources:
            try:
                logger.info(f"Processing {resource.identifier} (engine: {resource.engine}, status: {resource.status})")
                
                # Skip read replicas
                if rds_manager.is_read_replica(resource, all_read_replicas):
                    logger.info(f"Skipping read replica: {resource.identifier}")
                    skipped_resources.append({
                        'identifier': resource.identifier,
                        'reason': 'Read replica - cannot be stopped independently'
                    })
                    continue
                
                # Check for StopWeekEnd tag
                stop_time = tag_processor.get_time_tag_value(resource.tags, 'StopWeekEnd')
                
                if stop_time is None:
                    logger.debug(f"StopWeekEnd tag not found or invalid for {resource.identifier}")
                    skipped_resources.append({
                        'identifier': resource.identifier,
                        'reason': 'StopWeekEnd tag not set or invalid format'
                    })
                    continue
                
                # Check if current time matches the scheduled time
                if not tz_manager.is_time_in_range(stop_time):
                    logger.debug(f"Not time to stop {resource.identifier} (scheduled: {stop_time})")
                    skipped_resources.append({
                        'identifier': resource.identifier,
                        'reason': f'Not scheduled time (scheduled: {stop_time})'
                    })
                    continue
                
                logger.info(f"Time to stop {resource.identifier} (scheduled: {stop_time})")
                
                # Validate engine compatibility
                if resource.is_cluster and not rds_manager.is_aurora_engine(resource.engine):
                    logger.warning(f"Non-Aurora engine in cluster format: {resource.identifier}")
                    skipped_resources.append({
                        'identifier': resource.identifier,
                        'reason': 'Non-Aurora engine in cluster format'
                    })
                    continue
                
                if not resource.is_cluster and rds_manager.is_aurora_engine(resource.engine):
                    logger.warning(f"Aurora engine in instance format: {resource.identifier}")
                    skipped_resources.append({
                        'identifier': resource.identifier,
                        'reason': 'Aurora engine should be managed as cluster'
                    })
                    continue
                
                # Attempt to stop the resource
                if rds_manager.stop_rds_resource(resource):
                    stopped_resources.append({
                        'identifier': resource.identifier,
                        'type': 'cluster' if resource.is_cluster else 'instance',
                        'engine': resource.engine,
                        'scheduled_time': stop_time
                    })
                else:
                    skipped_resources.append({
                        'identifier': resource.identifier,
                        'reason': f'Not in available state (current: {resource.status})'
                    })
                    
            except Exception as e:
                logger.error(f"Error processing resource {resource.identifier}: {e}")
                error_resources.append({
                    'identifier': resource.identifier,
                    'error': str(e)
                })
        
        # Prepare response
        total_processed = len(stopped_resources) + len(skipped_resources) + len(error_resources)
        
        response_details = {
            'timezone': timezone,
            'is_weekend': True,
            'total_resources_found': len(all_resources),
            'total_processed': total_processed,
            'stopped_count': len(stopped_resources),
            'skipped_count': len(skipped_resources),
            'error_count': len(error_resources),
            'stopped_resources': stopped_resources,
            'skipped_resources': skipped_resources,
            'error_resources': error_resources
        }
        
        success = len(error_resources) == 0
        message = f"WeekEnd stop completed. Stopped: {len(stopped_resources)}, Skipped: {len(skipped_resources)}, Errors: {len(error_resources)}"
        
        logger.info(message)
        if stopped_resources:
            logger.info(f"Stopped resources: {[r['identifier'] for r in stopped_resources]}")
        
        return create_lambda_response(success, message, response_details)
        
    except Exception as e:
        error_message = f"Unexpected error in lambda handler: {e}"
        logger.error(error_message, exc_info=True)
        return create_lambda_response(False, error_message, {'error_type': type(e).__name__})


# For testing purposes
if __name__ == "__main__":
    # Mock event and context for local testing
    test_event = {}
    
    class MockContext:
        def __init__(self):
            self.function_name = "RDSStopWeekEnd"
            self.function_version = "$LATEST"
            self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:RDSStopWeekEnd"
            self.memory_limit_in_mb = 128
            self.remaining_time_in_millis = 60000
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
