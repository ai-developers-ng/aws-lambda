"""
RDS Utilities Module

This module provides shared utilities for RDS start/stop operations,
eliminating code duplication and improving maintainability.

Author: Improved by AI Assistant
Version: 2.0.0
"""

import boto3
import logging
import os
import time
import datetime
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
from botocore.exceptions import ClientError, BotoCoreError


class RDSEngine(Enum):
    """Enumeration of supported RDS engines."""
    AURORA_MYSQL = "aurora-mysql"
    AURORA_POSTGRESQL = "aurora-postgresql"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MARIADB = "mariadb"
    ORACLE = "oracle-ee"
    SQLSERVER = "sqlserver-ex"


class RDSStatus(Enum):
    """Enumeration of RDS instance/cluster statuses."""
    AVAILABLE = "available"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    BACKING_UP = "backing-up"
    MODIFYING = "modifying"


@dataclass
class RDSResource:
    """Data class representing an RDS resource (instance or cluster)."""
    identifier: str
    arn: str
    engine: str
    status: str
    is_cluster: bool
    read_replicas: List[str]
    tags: Dict[str, str]


class RDSManager:
    """
    Enhanced RDS Manager with improved error handling, logging, and efficiency.
    """
    
    def __init__(self, region: Optional[str] = None):
        """
        Initialize RDS Manager.
        
        Args:
            region: AWS region. If None, uses AWS_REGION environment variable.
        """
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.rds_client = boto3.client('rds', region_name=self.region)
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """Set up structured logging."""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def get_all_rds_resources(self) -> Tuple[List[RDSResource], List[RDSResource]]:
        """
        Get all RDS instances and clusters with their metadata.
        
        Returns:
            Tuple of (instances, clusters) as RDSResource objects.
        """
        instances = []
        clusters = []
        
        try:
            # Get all DB instances
            paginator = self.rds_client.get_paginator('describe_db_instances')
            for page in paginator.paginate():
                for db in page['DBInstances']:
                    try:
                        tags = self._get_resource_tags(db['DBInstanceArn'])
                        resource = RDSResource(
                            identifier=db['DBInstanceIdentifier'],
                            arn=db['DBInstanceArn'],
                            engine=db['Engine'],
                            status=db['DBInstanceStatus'],
                            is_cluster=False,
                            read_replicas=db.get('ReadReplicaDBInstanceIdentifiers', []),
                            tags=tags
                        )
                        instances.append(resource)
                    except Exception as e:
                        self.logger.error(f"Error processing instance {db.get('DBInstanceIdentifier', 'unknown')}: {e}")
                        
        except ClientError as e:
            self.logger.error(f"Error describing DB instances: {e}")
            
        try:
            # Get all DB clusters
            paginator = self.rds_client.get_paginator('describe_db_clusters')
            for page in paginator.paginate():
                for db in page['DBClusters']:
                    try:
                        tags = self._get_resource_tags(db['DBClusterArn'])
                        resource = RDSResource(
                            identifier=db['DBClusterIdentifier'],
                            arn=db['DBClusterArn'],
                            engine=db['Engine'],
                            status=db['Status'],
                            is_cluster=True,
                            read_replicas=db.get('ReadReplicaIdentifiers', []),
                            tags=tags
                        )
                        clusters.append(resource)
                    except Exception as e:
                        self.logger.error(f"Error processing cluster {db.get('DBClusterIdentifier', 'unknown')}: {e}")
                        
        except ClientError as e:
            self.logger.error(f"Error describing DB clusters: {e}")
            
        self.logger.info(f"Found {len(instances)} instances and {len(clusters)} clusters")
        return instances, clusters
    
    def _get_resource_tags(self, resource_arn: str) -> Dict[str, str]:
        """
        Get tags for an RDS resource.
        
        Args:
            resource_arn: ARN of the RDS resource.
            
        Returns:
            Dictionary of tag key-value pairs.
        """
        try:
            response = self.rds_client.list_tags_for_resource(ResourceName=resource_arn)
            return {tag['Key']: tag['Value'] for tag in response['TagList']}
        except ClientError as e:
            self.logger.error(f"Error getting tags for {resource_arn}: {e}")
            return {}
    
    def is_aurora_engine(self, engine: str) -> bool:
        """Check if the engine is Aurora."""
        return engine in [RDSEngine.AURORA_MYSQL.value, RDSEngine.AURORA_POSTGRESQL.value]
    
    def is_read_replica(self, resource: RDSResource, all_read_replicas: List[str]) -> bool:
        """
        Check if a resource is a read replica.
        
        Args:
            resource: RDS resource to check.
            all_read_replicas: List of all read replica identifiers.
            
        Returns:
            True if the resource is a read replica.
        """
        return (resource.identifier in all_read_replicas or 
                len(resource.read_replicas) > 0)
    
    def get_all_read_replicas(self, resources: List[RDSResource]) -> List[str]:
        """
        Get all read replica identifiers from a list of resources.
        
        Args:
            resources: List of RDS resources.
            
        Returns:
            List of read replica identifiers.
        """
        read_replicas = []
        for resource in resources:
            read_replicas.extend(resource.read_replicas)
        return read_replicas
    
    def start_rds_resource(self, resource: RDSResource) -> bool:
        """
        Start an RDS resource (instance or cluster).
        
        Args:
            resource: RDS resource to start.
            
        Returns:
            True if start operation was initiated successfully.
        """
        try:
            if resource.status != RDSStatus.STOPPED.value:
                self.logger.info(f"{resource.identifier} is not in stopped state (current: {resource.status})")
                return False
                
            if resource.is_cluster:
                self.rds_client.start_db_cluster(DBClusterIdentifier=resource.identifier)
                self.logger.info(f"Started cluster: {resource.identifier}")
            else:
                self.rds_client.start_db_instance(DBInstanceIdentifier=resource.identifier)
                self.logger.info(f"Started instance: {resource.identifier}")
                
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidDBInstanceState':
                self.logger.warning(f"Cannot start {resource.identifier}: Invalid state")
            elif error_code == 'DBInstanceNotFound':
                self.logger.error(f"Resource not found: {resource.identifier}")
            else:
                self.logger.error(f"Error starting {resource.identifier}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error starting {resource.identifier}: {e}")
            return False
    
    def stop_rds_resource(self, resource: RDSResource) -> bool:
        """
        Stop an RDS resource (instance or cluster).
        
        Args:
            resource: RDS resource to stop.
            
        Returns:
            True if stop operation was initiated successfully.
        """
        try:
            if resource.status != RDSStatus.AVAILABLE.value:
                self.logger.info(f"{resource.identifier} is not in available state (current: {resource.status})")
                return False
                
            if resource.is_cluster:
                self.rds_client.stop_db_cluster(DBClusterIdentifier=resource.identifier)
                self.logger.info(f"Stopped cluster: {resource.identifier}")
            else:
                self.rds_client.stop_db_instance(DBInstanceIdentifier=resource.identifier)
                self.logger.info(f"Stopped instance: {resource.identifier}")
                
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidDBInstanceState':
                self.logger.warning(f"Cannot stop {resource.identifier}: Invalid state")
            elif error_code == 'DBInstanceNotFound':
                self.logger.error(f"Resource not found: {resource.identifier}")
            else:
                self.logger.error(f"Error stopping {resource.identifier}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error stopping {resource.identifier}: {e}")
            return False


class TimeZoneManager:
    """
    Enhanced timezone management with better error handling.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def set_timezone(self, timezone: Optional[str] = None) -> str:
        """
        Set the timezone for the Lambda function.
        
        Args:
            timezone: Timezone string. If None, uses REGION_TZ or TZ environment variable.
            
        Returns:
            The timezone that was set.
        """
        if not timezone:
            timezone = os.environ.get('REGION_TZ') or os.environ.get('TZ', 'UTC')
        
        if not timezone or timezone == '':
            timezone = 'UTC'
            
        try:
            os.environ['TZ'] = timezone
            time.tzset()
            self.logger.info(f"Timezone set to: {timezone}")
            return timezone
        except Exception as e:
            self.logger.error(f"Error setting timezone to {timezone}: {e}")
            # Fallback to UTC
            os.environ['TZ'] = 'UTC'
            time.tzset()
            return 'UTC'
    
    def is_time_in_range(self, target_time: str, tolerance_minutes: int = 5) -> bool:
        """
        Check if current time is within the target time range.
        
        Args:
            target_time: Target time in HH:MM format.
            tolerance_minutes: Tolerance in minutes (default: 5).
            
        Returns:
            True if current time is within the target range.
        """
        try:
            now = datetime.datetime.now()
            current_time = now.strftime('%H:%M')
            
            # Calculate time range
            time_minus = (now - datetime.timedelta(minutes=tolerance_minutes)).strftime('%H:%M')
            time_plus = (now + datetime.timedelta(minutes=tolerance_minutes)).strftime('%H:%M')
            
            # Handle day boundary crossing
            if time_minus <= time_plus:
                return time_minus <= target_time <= time_plus
            else:
                # Crosses midnight
                return target_time >= time_minus or target_time <= time_plus
                
        except Exception as e:
            self.logger.error(f"Error checking time range for {target_time}: {e}")
            return False
    
    def is_weekday(self) -> bool:
        """Check if current day is a weekday (Monday-Friday)."""
        return 1 <= datetime.datetime.now().isoweekday() <= 5
    
    def is_weekend(self) -> bool:
        """Check if current day is a weekend (Saturday-Sunday)."""
        return 6 <= datetime.datetime.now().isoweekday() <= 7


class TagProcessor:
    """
    Enhanced tag processing with validation and better error handling.
    """
    
    VALID_BOOLEAN_VALUES = {'true', 'false', '1', '0', 'yes', 'no', 'on', 'off'}
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_boolean_tag_value(self, tags: Dict[str, str], tag_key: str) -> Optional[bool]:
        """
        Get boolean value from tags with validation.
        
        Args:
            tags: Dictionary of tags.
            tag_key: Tag key to look for.
            
        Returns:
            Boolean value or None if tag doesn't exist or is invalid.
        """
        tag_value = tags.get(tag_key, '').lower().strip()
        
        if not tag_value:
            return None
            
        if tag_value not in self.VALID_BOOLEAN_VALUES:
            self.logger.warning(f"Invalid boolean value for tag {tag_key}: {tag_value}")
            return None
            
        return tag_value in {'true', '1', 'yes', 'on'}
    
    def get_time_tag_value(self, tags: Dict[str, str], tag_key: str) -> Optional[str]:
        """
        Get and validate time value from tags.
        
        Args:
            tags: Dictionary of tags.
            tag_key: Tag key to look for.
            
        Returns:
            Time string in HH:MM format or None if invalid.
        """
        tag_value = tags.get(tag_key, '').strip()
        
        if not tag_value:
            return None
            
        # Validate HH:MM format
        try:
            time_parts = tag_value.split(':')
            if len(time_parts) != 2:
                raise ValueError("Invalid format")
                
            hours, minutes = int(time_parts[0]), int(time_parts[1])
            
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Invalid time values")
                
            return f"{hours:02d}:{minutes:02d}"
            
        except (ValueError, IndexError) as e:
            self.logger.warning(f"Invalid time format for tag {tag_key}: {tag_value}")
            return None


def create_lambda_response(success: bool, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create standardized Lambda response.
    
    Args:
        success: Whether the operation was successful.
        message: Response message.
        details: Additional details to include.
        
    Returns:
        Standardized response dictionary.
    """
    response = {
        'statusCode': 200 if success else 500,
        'success': success,
        'message': message,
        'timestamp': datetime.datetime.utcnow().isoformat()
    }
    
    if details:
        response['details'] = details
        
    return response
