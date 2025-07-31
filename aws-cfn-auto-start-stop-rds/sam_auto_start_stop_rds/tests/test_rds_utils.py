"""
Unit tests for RDS utilities module.

This module contains comprehensive tests for the improved RDS utilities,
ensuring reliability and correctness of the auto start/stop functionality.

Author: Improved by AI Assistant
Version: 2.0.0
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import boto3
from moto import mock_rds
import pytest
from datetime import datetime, timedelta
import os
import sys

# Add the lambda_layer to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda_layer', 'python'))

from rds_utils import (
    RDSManager, TagProcessor, TimeZoneManager, RDSResource, 
    RDSEngine, RDSStatus, create_lambda_response
)


class TestRDSResource(unittest.TestCase):
    """Test RDSResource data class."""
    
    def test_rds_resource_creation(self):
        """Test RDSResource creation with valid data."""
        resource = RDSResource(
            identifier="test-db",
            arn="arn:aws:rds:us-east-1:123456789012:db:test-db",
            engine="mysql",
            status="available",
            is_cluster=False,
            read_replicas=[],
            tags={"AutoStart": "true"}
        )
        
        self.assertEqual(resource.identifier, "test-db")
        self.assertEqual(resource.engine, "mysql")
        self.assertFalse(resource.is_cluster)
        self.assertEqual(resource.tags["AutoStart"], "true")


class TestTagProcessor(unittest.TestCase):
    """Test TagProcessor functionality."""
    
    def setUp(self):
        self.processor = TagProcessor()
    
    def test_get_boolean_tag_value_valid(self):
        """Test boolean tag processing with valid values."""
        tags = {"AutoStart": "true", "AutoStop": "false", "Test": "yes"}
        
        self.assertTrue(self.processor.get_boolean_tag_value(tags, "AutoStart"))
        self.assertFalse(self.processor.get_boolean_tag_value(tags, "AutoStop"))
        self.assertTrue(self.processor.get_boolean_tag_value(tags, "Test"))
    
    def test_get_boolean_tag_value_invalid(self):
        """Test boolean tag processing with invalid values."""
        tags = {"Invalid": "maybe", "Empty": "", "Missing": None}
        
        self.assertIsNone(self.processor.get_boolean_tag_value(tags, "Invalid"))
        self.assertIsNone(self.processor.get_boolean_tag_value(tags, "Empty"))
        self.assertIsNone(self.processor.get_boolean_tag_value(tags, "NonExistent"))
    
    def test_get_time_tag_value_valid(self):
        """Test time tag processing with valid values."""
        tags = {"StartTime": "09:30", "StopTime": "18:00"}
        
        self.assertEqual(self.processor.get_time_tag_value(tags, "StartTime"), "09:30")
        self.assertEqual(self.processor.get_time_tag_value(tags, "StopTime"), "18:00")
    
    def test_get_time_tag_value_invalid(self):
        """Test time tag processing with invalid values."""
        tags = {
            "Invalid1": "25:00",  # Invalid hour
            "Invalid2": "12:60",  # Invalid minute
            "Invalid3": "12",     # Missing minute
            "Invalid4": "12:30:45",  # Too many parts
            "Empty": ""
        }
        
        for key in tags:
            self.assertIsNone(self.processor.get_time_tag_value(tags, key))


class TestTimeZoneManager(unittest.TestCase):
    """Test TimeZoneManager functionality."""
    
    def setUp(self):
        self.tz_manager = TimeZoneManager()
    
    @patch.dict(os.environ, {'REGION_TZ': 'US/Eastern'})
    def test_set_timezone_from_env(self):
        """Test timezone setting from environment variable."""
        timezone = self.tz_manager.set_timezone()
        self.assertEqual(timezone, 'US/Eastern')
    
    def test_set_timezone_fallback(self):
        """Test timezone fallback to UTC."""
        with patch.dict(os.environ, {}, clear=True):
            timezone = self.tz_manager.set_timezone()
            self.assertEqual(timezone, 'UTC')
    
    def test_is_time_in_range(self):
        """Test time range checking."""
        # Mock current time to 10:00
        with patch('datetime.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.strftime.return_value = "10:00"
            mock_datetime.now.return_value = mock_now
            mock_datetime.timedelta = timedelta
            
            # Mock timedelta operations
            mock_minus = Mock()
            mock_minus.strftime.return_value = "09:55"
            mock_plus = Mock()
            mock_plus.strftime.return_value = "10:05"
            
            # Test time within range
            self.assertTrue(self.tz_manager.is_time_in_range("10:00"))
            self.assertTrue(self.tz_manager.is_time_in_range("09:58"))
            self.assertTrue(self.tz_manager.is_time_in_range("10:03"))
    
    @patch('datetime.datetime')
    def test_is_weekday(self, mock_datetime):
        """Test weekday detection."""
        # Monday (1)
        mock_datetime.now.return_value.isoweekday.return_value = 1
        self.assertTrue(self.tz_manager.is_weekday())
        
        # Saturday (6)
        mock_datetime.now.return_value.isoweekday.return_value = 6
        self.assertFalse(self.tz_manager.is_weekday())
    
    @patch('datetime.datetime')
    def test_is_weekend(self, mock_datetime):
        """Test weekend detection."""
        # Saturday (6)
        mock_datetime.now.return_value.isoweekday.return_value = 6
        self.assertTrue(self.tz_manager.is_weekend())
        
        # Monday (1)
        mock_datetime.now.return_value.isoweekday.return_value = 1
        self.assertFalse(self.tz_manager.is_weekend())


@mock_rds
class TestRDSManager(unittest.TestCase):
    """Test RDSManager functionality with mocked AWS services."""
    
    def setUp(self):
        self.rds_manager = RDSManager(region='us-east-1')
        
        # Create mock RDS client
        self.rds_client = boto3.client('rds', region_name='us-east-1')
        
        # Create test DB instance
        self.rds_client.create_db_instance(
            DBInstanceIdentifier='test-db',
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            MasterUsername='admin',
            MasterUserPassword='password123',
            AllocatedStorage=20
        )
    
    def test_get_all_rds_resources(self):
        """Test getting all RDS resources."""
        with patch.object(self.rds_manager, 'rds_client', self.rds_client):
            with patch.object(self.rds_manager, '_get_resource_tags', return_value={}):
                instances, clusters = self.rds_manager.get_all_rds_resources()
                
                self.assertEqual(len(instances), 1)
                self.assertEqual(len(clusters), 0)
                self.assertEqual(instances[0].identifier, 'test-db')
    
    def test_is_aurora_engine(self):
        """Test Aurora engine detection."""
        self.assertTrue(self.rds_manager.is_aurora_engine('aurora-mysql'))
        self.assertTrue(self.rds_manager.is_aurora_engine('aurora-postgresql'))
        self.assertFalse(self.rds_manager.is_aurora_engine('mysql'))
        self.assertFalse(self.rds_manager.is_aurora_engine('postgresql'))
    
    def test_is_read_replica(self):
        """Test read replica detection."""
        resource = RDSResource(
            identifier="replica-db",
            arn="arn:aws:rds:us-east-1:123456789012:db:replica-db",
            engine="mysql",
            status="available",
            is_cluster=False,
            read_replicas=[],
            tags={}
        )
        
        all_read_replicas = ["replica-db", "another-replica"]
        
        self.assertTrue(self.rds_manager.is_read_replica(resource, all_read_replicas))
        
        # Test with resource that has read replicas
        resource.read_replicas = ["child-replica"]
        self.assertTrue(self.rds_manager.is_read_replica(resource, []))
    
    def test_get_all_read_replicas(self):
        """Test getting all read replicas from resources."""
        resources = [
            RDSResource("db1", "arn1", "mysql", "available", False, ["replica1", "replica2"], {}),
            RDSResource("db2", "arn2", "mysql", "available", False, ["replica3"], {}),
            RDSResource("db3", "arn3", "mysql", "available", False, [], {})
        ]
        
        read_replicas = self.rds_manager.get_all_read_replicas(resources)
        self.assertEqual(set(read_replicas), {"replica1", "replica2", "replica3"})
    
    @patch('boto3.client')
    def test_start_rds_resource_success(self, mock_boto_client):
        """Test successful RDS resource start."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        resource = RDSResource(
            identifier="test-db",
            arn="arn:aws:rds:us-east-1:123456789012:db:test-db",
            engine="mysql",
            status="stopped",
            is_cluster=False,
            read_replicas=[],
            tags={}
        )
        
        manager = RDSManager()
        manager.rds_client = mock_client
        
        result = manager.start_rds_resource(resource)
        
        self.assertTrue(result)
        mock_client.start_db_instance.assert_called_once_with(DBInstanceIdentifier="test-db")
    
    @patch('boto3.client')
    def test_stop_rds_resource_success(self, mock_boto_client):
        """Test successful RDS resource stop."""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        resource = RDSResource(
            identifier="test-db",
            arn="arn:aws:rds:us-east-1:123456789012:db:test-db",
            engine="mysql",
            status="available",
            is_cluster=False,
            read_replicas=[],
            tags={}
        )
        
        manager = RDSManager()
        manager.rds_client = mock_client
        
        result = manager.stop_rds_resource(resource)
        
        self.assertTrue(result)
        mock_client.stop_db_instance.assert_called_once_with(DBInstanceIdentifier="test-db")


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions."""
    
    def test_create_lambda_response_success(self):
        """Test creating successful Lambda response."""
        response = create_lambda_response(True, "Operation successful", {"count": 5})
        
        self.assertEqual(response['statusCode'], 200)
        self.assertTrue(response['success'])
        self.assertEqual(response['message'], "Operation successful")
        self.assertEqual(response['details']['count'], 5)
        self.assertIn('timestamp', response)
    
    def test_create_lambda_response_error(self):
        """Test creating error Lambda response."""
        response = create_lambda_response(False, "Operation failed")
        
        self.assertEqual(response['statusCode'], 500)
        self.assertFalse(response['success'])
        self.assertEqual(response['message'], "Operation failed")
        self.assertIn('timestamp', response)


if __name__ == '__main__':
    # Set up test environment
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    
    # Run tests
    unittest.main(verbosity=2)
