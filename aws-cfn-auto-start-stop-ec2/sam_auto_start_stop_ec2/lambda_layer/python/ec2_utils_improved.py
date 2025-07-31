"""
Enhanced EC2 Utilities for Auto Start/Stop Lambda Functions

This module provides comprehensive utilities for managing EC2 instances with improved
error handling, security, performance, and monitoring capabilities.

Author: Enhanced by BlackBoxAI
Version: 2.0.0
Python: 3.11+
"""

import boto3
import logging
import os
import time
import datetime
import json
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass, asdict
from enum import Enum
from botocore.exceptions import ClientError, BotoCoreError
import re


class InstanceState(Enum):
    """EC2 Instance states"""
    PENDING = "pending"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting-down"
    TERMINATED = "terminated"
    STOPPING = "stopping"
    STOPPED = "stopped"


class ActionType(Enum):
    """Action types for EC2 operations"""
    START = "start"
    STOP = "stop"


@dataclass
class EC2Resource:
    """Represents an EC2 instance with relevant metadata"""
    instance_id: str
    state: str
    instance_type: str
    availability_zone: str
    tags: Dict[str, str]
    launch_time: Optional[datetime.datetime] = None
    private_ip: Optional[str] = None
    public_ip: Optional[str] = None


@dataclass
class OperationResult:
    """Result of an EC2 operation"""
    success: bool
    instance_id: str
    action: str
    message: str
    error_code: Optional[str] = None
    timestamp: datetime.datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.datetime.utcnow()


class EC2Manager:
    """Enhanced EC2 management with comprehensive error handling and monitoring"""
    
    def __init__(self, region: Optional[str] = None):
        """
        Initialize EC2Manager
        
        Args:
            region: AWS region (defaults to environment variable)
        """
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.logger = self._setup_logger()
        
        try:
            self.ec2_client = boto3.client('ec2', region_name=self.region)
            self.ec2_resource = boto3.resource('ec2', region_name=self.region)
        except Exception as e:
            self.logger.error(f"Failed to initialize EC2 clients: {e}")
            raise
    
    def _setup_logger(self) -> logging.Logger:
        """Setup structured logging"""
        logger = logging.getLogger(f"EC2Manager-{self.region}")
        
        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create handler with structured format
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())
        
        return logger
    
    def get_instances_by_tag(
        self, 
        tag_name: str, 
        tag_values: List[str], 
        instance_states: Optional[List[str]] = None
    ) -> List[EC2Resource]:
        """
        Get EC2 instances by tag with enhanced filtering and error handling
        
        Args:
            tag_name: Tag key to filter by
            tag_values: List of tag values to match
            instance_states: Optional list of instance states to filter by
            
        Returns:
            List of EC2Resource objects
        """
        try:
            filters = [
                {
                    'Name': f'tag:{tag_name}',
                    'Values': tag_values
                }
            ]
            
            if instance_states:
                filters.append({
                    'Name': 'instance-state-name',
                    'Values': instance_states
                })
            
            self.logger.info(f"Querying instances with tag {tag_name} in values {tag_values}")
            
            paginator = self.ec2_client.get_paginator('describe_instances')
            instances = []
            
            for page in paginator.paginate(Filters=filters):
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        instances.append(self._create_ec2_resource(instance))
            
            self.logger.info(f"Found {len(instances)} instances matching criteria")
            return instances
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            self.logger.error(f"AWS API error getting instances by tag: {error_code} - {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error getting instances by tag: {e}")
            raise
    
    def get_instances_by_time_tag(
        self,
        tag_name: str,
        current_time: datetime.datetime,
        time_window_minutes: int = 5,
        weekday_filter: Optional[Tuple[int, int]] = None
    ) -> List[EC2Resource]:
        """
        Get instances by time-based tags with enhanced validation
        
        Args:
            tag_name: Time tag to filter by (e.g., 'StartWeekDay')
            current_time: Current datetime
            time_window_minutes: Time window for matching
            weekday_filter: Tuple of (min_weekday, max_weekday) for filtering
            
        Returns:
            List of matching EC2Resource objects
        """
        try:
            self.logger.info(f"Searching for instances with time tag {tag_name}")
            
            # Get all instances (we'll filter by time locally)
            paginator = self.ec2_client.get_paginator('describe_instances')
            matching_instances = []
            
            # Calculate time window
            time_plus = current_time + datetime.timedelta(minutes=time_window_minutes)
            time_minus = current_time - datetime.timedelta(minutes=time_window_minutes)
            current_time_str = current_time.strftime('%H:%M')
            max_time_str = time_plus.strftime('%H:%M')
            min_time_str = time_minus.strftime('%H:%M')
            current_weekday = current_time.isoweekday()
            
            self.logger.info(
                f"Time window: {min_time_str} - {max_time_str}, "
                f"Current weekday: {current_weekday}"
            )
            
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        if 'Tags' in instance:
                            for tag in instance['Tags']:
                                if tag['Key'] == tag_name:
                                    scheduled_time = tag['Value']
                                    
                                    # Validate time format
                                    if not self._validate_time_format(scheduled_time):
                                        self.logger.warning(
                                            f"Invalid time format '{scheduled_time}' for instance "
                                            f"{instance['InstanceId']}"
                                        )
                                        continue
                                    
                                    # Check if time matches within window
                                    time_matches = min_time_str <= scheduled_time <= max_time_str
                                    
                                    # Check weekday filter if provided
                                    weekday_matches = True
                                    if weekday_filter:
                                        min_day, max_day = weekday_filter
                                        weekday_matches = min_day <= current_weekday <= max_day
                                    
                                    if time_matches and weekday_matches:
                                        ec2_resource = self._create_ec2_resource(instance)
                                        matching_instances.append(ec2_resource)
                                        self.logger.info(
                                            f"Found matching instance {instance['InstanceId']} "
                                            f"with scheduled time {scheduled_time}"
                                        )
                                    break
            
            self.logger.info(f"Found {len(matching_instances)} instances with matching schedule")
            return matching_instances
            
        except Exception as e:
            self.logger.error(f"Error getting instances by time tag: {e}")
            raise
    
    def start_instances(self, instances: List[EC2Resource]) -> List[OperationResult]:
        """
        Start EC2 instances with comprehensive error handling
        
        Args:
            instances: List of EC2Resource objects to start
            
        Returns:
            List of OperationResult objects
        """
        results = []
        
        for instance in instances:
            result = self._start_single_instance(instance)
            results.append(result)
        
        # Log summary
        successful = sum(1 for r in results if r.success)
        self.logger.info(f"Start operation completed: {successful}/{len(results)} successful")
        
        return results
    
    def stop_instances(self, instances: List[EC2Resource]) -> List[OperationResult]:
        """
        Stop EC2 instances with comprehensive error handling
        
        Args:
            instances: List of EC2Resource objects to stop
            
        Returns:
            List of OperationResult objects
        """
        results = []
        
        for instance in instances:
            result = self._stop_single_instance(instance)
            results.append(result)
        
        # Log summary
        successful = sum(1 for r in results if r.success)
        self.logger.info(f"Stop operation completed: {successful}/{len(results)} successful")
        
        return results
    
    def _start_single_instance(self, instance: EC2Resource) -> OperationResult:
        """Start a single EC2 instance with retry logic"""
        try:
            # Check current state
            if instance.state != InstanceState.STOPPED.value:
                return OperationResult(
                    success=False,
                    instance_id=instance.instance_id,
                    action=ActionType.START.value,
                    message=f"Instance not in stopped state (current: {instance.state})"
                )
            
            # Attempt to start instance
            response = self.ec2_client.start_instances(InstanceIds=[instance.instance_id])
            
            # Verify the start was initiated
            if response['StartingInstances']:
                starting_instance = response['StartingInstances'][0]
                current_state = starting_instance['CurrentState']['Name']
                
                self.logger.info(f"Successfully initiated start for {instance.instance_id}")
                
                return OperationResult(
                    success=True,
                    instance_id=instance.instance_id,
                    action=ActionType.START.value,
                    message=f"Start initiated, current state: {current_state}"
                )
            else:
                return OperationResult(
                    success=False,
                    instance_id=instance.instance_id,
                    action=ActionType.START.value,
                    message="No starting instances returned in response"
                )
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            self.logger.error(f"AWS API error starting {instance.instance_id}: {error_code} - {error_message}")
            
            return OperationResult(
                success=False,
                instance_id=instance.instance_id,
                action=ActionType.START.value,
                message=f"AWS API error: {error_message}",
                error_code=error_code
            )
        except Exception as e:
            self.logger.error(f"Unexpected error starting {instance.instance_id}: {e}")
            
            return OperationResult(
                success=False,
                instance_id=instance.instance_id,
                action=ActionType.START.value,
                message=f"Unexpected error: {str(e)}"
            )
    
    def _stop_single_instance(self, instance: EC2Resource) -> OperationResult:
        """Stop a single EC2 instance with retry logic"""
        try:
            # Check current state
            if instance.state != InstanceState.RUNNING.value:
                return OperationResult(
                    success=False,
                    instance_id=instance.instance_id,
                    action=ActionType.STOP.value,
                    message=f"Instance not in running state (current: {instance.state})"
                )
            
            # Attempt to stop instance
            response = self.ec2_client.stop_instances(InstanceIds=[instance.instance_id])
            
            # Verify the stop was initiated
            if response['StoppingInstances']:
                stopping_instance = response['StoppingInstances'][0]
                current_state = stopping_instance['CurrentState']['Name']
                
                self.logger.info(f"Successfully initiated stop for {instance.instance_id}")
                
                return OperationResult(
                    success=True,
                    instance_id=instance.instance_id,
                    action=ActionType.STOP.value,
                    message=f"Stop initiated, current state: {current_state}"
                )
            else:
                return OperationResult(
                    success=False,
                    instance_id=instance.instance_id,
                    action=ActionType.STOP.value,
                    message="No stopping instances returned in response"
                )
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            self.logger.error(f"AWS API error stopping {instance.instance_id}: {error_code} - {error_message}")
            
            return OperationResult(
                success=False,
                instance_id=instance.instance_id,
                action=ActionType.STOP.value,
                message=f"AWS API error: {error_message}",
                error_code=error_code
            )
        except Exception as e:
            self.logger.error(f"Unexpected error stopping {instance.instance_id}: {e}")
            
            return OperationResult(
                success=False,
                instance_id=instance.instance_id,
                action=ActionType.STOP.value,
                message=f"Unexpected error: {str(e)}"
            )
    
    def _create_ec2_resource(self, instance_data: Dict) -> EC2Resource:
        """Create EC2Resource from AWS API response"""
        tags = {}
        if 'Tags' in instance_data:
            tags = {tag['Key']: tag['Value'] for tag in instance_data['Tags']}
        
        return EC2Resource(
            instance_id=instance_data['InstanceId'],
            state=instance_data['State']['Name'],
            instance_type=instance_data['InstanceType'],
            availability_zone=instance_data['Placement']['AvailabilityZone'],
            tags=tags,
            launch_time=instance_data.get('LaunchTime'),
            private_ip=instance_data.get('PrivateIpAddress'),
            public_ip=instance_data.get('PublicIpAddress')
        )
    
    def _validate_time_format(self, time_str: str) -> bool:
        """Validate time format (HH:MM)"""
        pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
        return bool(re.match(pattern, time_str))


class TimezoneManager:
    """Enhanced timezone management with validation"""
    
    SUPPORTED_TIMEZONES = {
        'UTC': 'UTC',
        'US/Eastern': 'US/Eastern',
        'US/Pacific': 'US/Pacific',
        'US/Central': 'US/Central',
        'US/Mountain': 'US/Mountain',
        'Europe/London': 'Europe/London',
        'Europe/Paris': 'Europe/Paris',
        'Europe/Berlin': 'Europe/Berlin',
        'Asia/Tokyo': 'Asia/Tokyo',
        'Asia/Singapore': 'Asia/Singapore',
        'Asia/Kolkata': 'Asia/Kolkata',
        'Australia/Sydney': 'Australia/Sydney'
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def set_timezone(self, timezone_str: Optional[str] = None) -> str:
        """
        Set timezone with validation and fallback
        
        Args:
            timezone_str: Timezone string (defaults to environment variable)
            
        Returns:
            Applied timezone string
        """
        try:
            # Get timezone from parameter, environment, or default
            timezone = (
                timezone_str or 
                os.environ.get('REGION_TZ') or 
                os.environ.get('TZ') or 
                'UTC'
            )
            
            # Validate timezone
            if timezone not in self.SUPPORTED_TIMEZONES:
                self.logger.warning(f"Unsupported timezone '{timezone}', falling back to UTC")
                timezone = 'UTC'
            
            # Log current time before setting
            time_before = datetime.datetime.now()
            self.logger.info(f"Time before timezone setting: {time_before}")
            
            # Set timezone
            os.environ['TZ'] = timezone
            time.tzset()
            
            # Log current time after setting
            time_after = datetime.datetime.now()
            self.logger.info(f"Time after setting timezone to {timezone}: {time_after}")
            
            return timezone
            
        except Exception as e:
            self.logger.error(f"Error setting timezone: {e}, falling back to UTC")
            os.environ['TZ'] = 'UTC'
            time.tzset()
            return 'UTC'


class TagValidator:
    """Enhanced tag validation with comprehensive checks"""
    
    BOOLEAN_TRUE_VALUES = {'true', 'True', 'TRUE', '1', 'yes', 'Yes', 'YES', 'on', 'On', 'ON'}
    BOOLEAN_FALSE_VALUES = {'false', 'False', 'FALSE', '0', 'no', 'No', 'NO', 'off', 'Off', 'OFF'}
    
    @staticmethod
    def validate_boolean_tag(tag_value: str) -> bool:
        """
        Validate boolean tag values with comprehensive checking
        
        Args:
            tag_value: Tag value to validate
            
        Returns:
            True if tag value represents true, False otherwise
        """
        if not tag_value:
            return False
        
        tag_value = tag_value.strip()
        return tag_value in TagValidator.BOOLEAN_TRUE_VALUES
    
    @staticmethod
    def validate_time_tag(tag_value: str) -> bool:
        """
        Validate time tag format (HH:MM)
        
        Args:
            tag_value: Time string to validate
            
        Returns:
            True if valid time format, False otherwise
        """
        if not tag_value:
            return False
        
        pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
        return bool(re.match(pattern, tag_value.strip()))


def create_lambda_response(
    status_code: int,
    results: List[OperationResult],
    action: str,
    additional_info: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create standardized Lambda response
    
    Args:
        status_code: HTTP status code
        results: List of operation results
        action: Action performed
        additional_info: Additional information to include
        
    Returns:
        Standardized response dictionary
    """
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    
    response_body = {
        'action': action,
        'summary': {
            'total_processed': len(results),
            'successful': successful,
            'failed': failed
        },
        'results': [asdict(result) for result in results],
        'timestamp': datetime.datetime.utcnow().isoformat()
    }
    
    if additional_info:
        response_body.update(additional_info)
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps(response_body, default=str)
    }


def configure_logging(level: str = None) -> logging.Logger:
    """
    Configure enhanced logging for Lambda functions
    
    Args:
        level: Log level (defaults to environment variable or INFO)
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create new handler with enhanced formatting
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Set log level
    log_level = level or os.environ.get('LOG_LEVEL', 'INFO')
    logger.setLevel(log_level.upper())
    
    return logger


# Backward compatibility functions
def get_ec2_client():
    """Backward compatibility function"""
    return boto3.client('ec2')


def get_instances_by_tag(ec2_client, tag_name, tag_values, instance_states):
    """Backward compatibility function"""
    manager = EC2Manager()
    instances = manager.get_instances_by_tag(tag_name, tag_values, instance_states)
    return [instance.instance_id for instance in instances]


def start_ec2_instances(ec2_client, instance_ids):
    """Backward compatibility function"""
    if not instance_ids:
        return
    
    try:
        response = ec2_client.start_instances(InstanceIds=instance_ids)
        logging.info(f"Successfully initiated start for instances: {instance_ids}")
        return response
    except Exception as e:
        logging.error(f"Error starting instances {instance_ids}: {e}")
        raise


def stop_ec2_instances(ec2_client, instance_ids):
    """Backward compatibility function"""
    if not instance_ids:
        return
    
    try:
        response = ec2_client.stop_instances(InstanceIds=instance_ids)
        logging.info(f"Successfully initiated stop for instances: {instance_ids}")
        return response
    except Exception as e:
        logging.error(f"Error stopping instances {instance_ids}: {e}")
        raise


def set_region_timezone():
    """Backward compatibility function"""
    manager = TimezoneManager()
    return manager.set_timezone()


def get_instances_by_time_tag(ec2_client, tag_name, current_time, time_window_minutes=5, weekday_filter=None):
    """Backward compatibility function"""
    manager = EC2Manager()
    instances = manager.get_instances_by_time_tag(tag_name, current_time, time_window_minutes, weekday_filter)
    return [
        {
            'instance_id': instance.instance_id,
            'scheduled_time': instance.tags.get(tag_name, ''),
            'current_state': instance.state
        }
        for instance in instances
    ]


def process_time_based_instances(ec2_client, instances_data, target_state, action):
    """Backward compatibility function"""
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
