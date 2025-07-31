"""
Comprehensive Test Suite for Enhanced EC2 Utilities

This test suite provides comprehensive coverage for the improved EC2 utilities,
including unit tests, integration tests, and security validation tests.

Author: Enhanced by BlackBoxAI
Version: 2.0.0
Python: 3.11+
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import datetime
import json
import os
import sys
from typing import Dict, List

# Add the lambda layer to the path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda_layer', 'python'))

from ec2_utils_improved import (
    EC2Manager,
    TimezoneManager,
    TagValidator,
    EC2Resource,
    OperationResult,
    InstanceState,
    ActionType,
    create_lambda_response,
    configure_logging
)


class TestEC2Resource(unittest.TestCase):
    """Test EC2Resource dataclass"""
    
    def test_ec2_resource_creation(self):
        """Test EC2Resource creation with all fields"""
        resource = EC2Resource(
            instance_id='i-1234567890abcdef0',
            state='running',
            instance_type='t3.micro',
            availability_zone='us-east-1a',
            tags={'Name': 'TestInstance', 'AutoStart': 'true'},
            private_ip='10.0.1.100',
            public_ip='54.123.45.67'
        )
        
        self.assertEqual(resource.instance_id, 'i-1234567890abcdef0')
        self.assertEqual(resource.state, 'running')
        self.assertEqual(resource.instance_type, 't3.micro')
        self.assertEqual(resource.availability_zone, 'us-east-1a')
        self.assertEqual(resource.tags['Name'], 'TestInstance')
        self.assertEqual(resource.private_ip, '10.0.1.100')
        self.assertEqual(resource.public_ip, '54.123.45.67')
    
    def test_ec2_resource_minimal(self):
        """Test EC2Resource creation with minimal fields"""
        resource = EC2Resource(
            instance_id='i-1234567890abcdef0',
            state='stopped',
            instance_type='t3.micro',
            availability_zone='us-east-1a',
            tags={}
        )
        
        self.assertEqual(resource.instance_id, 'i-1234567890abcdef0')
        self.assertEqual(resource.state, 'stopped')
        self.assertIsNone(resource.launch_time)
        self.assertIsNone(resource.private_ip)
        self.assertIsNone(resource.public_ip)


class TestOperationResult(unittest.TestCase):
    """Test OperationResult dataclass"""
    
    def test_operation_result_success(self):
        """Test successful operation result"""
        result = OperationResult(
            success=True,
            instance_id='i-1234567890abcdef0',
            action='start',
            message='Instance started successfully'
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.instance_id, 'i-1234567890abcdef0')
        self.assertEqual(result.action, 'start')
        self.assertEqual(result.message, 'Instance started successfully')
        self.assertIsNone(result.error_code)
        self.assertIsNotNone(result.timestamp)
    
    def test_operation_result_failure(self):
        """Test failed operation result"""
        result = OperationResult(
            success=False,
            instance_id='i-1234567890abcdef0',
            action='stop',
            message='Instance not in running state',
            error_code='InvalidInstanceState'
        )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, 'InvalidInstanceState')


class TestTagValidator(unittest.TestCase):
    """Test TagValidator functionality"""
    
    def test_validate_boolean_tag_true_values(self):
        """Test boolean tag validation for true values"""
        true_values = ['true', 'True', 'TRUE', '1', 'yes', 'Yes', 'YES', 'on', 'On', 'ON']
        
        for value in true_values:
            with self.subTest(value=value):
                self.assertTrue(TagValidator.validate_boolean_tag(value))
    
    def test_validate_boolean_tag_false_values(self):
        """Test boolean tag validation for false values"""
        false_values = ['false', 'False', 'FALSE', '0', 'no', 'No', 'NO', 'off', 'Off', 'OFF', '']
        
        for value in false_values:
            with self.subTest(value=value):
                self.assertFalse(TagValidator.validate_boolean_tag(value))
    
    def test_validate_time_tag_valid(self):
        """Test time tag validation for valid formats"""
        valid_times = ['00:00', '09:30', '12:00', '18:45', '23:59']
        
        for time_str in valid_times:
            with self.subTest(time=time_str):
                self.assertTrue(TagValidator.validate_time_tag(time_str))
    
    def test_validate_time_tag_invalid(self):
        """Test time tag validation for invalid formats"""
        invalid_times = ['24:00', '12:60', '9:30', '12:5', 'invalid', '', '25:00', '12:99']
        
        for time_str in invalid_times:
            with self.subTest(time=time_str):
                self.assertFalse(TagValidator.validate_time_tag(time_str))


class TestTimezoneManager(unittest.TestCase):
    """Test TimezoneManager functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.timezone_manager = TimezoneManager()
    
    def test_set_timezone_valid(self):
        """Test setting valid timezone"""
        timezone = self.timezone_manager.set_timezone('US/Eastern')
        self.assertEqual(timezone, 'US/Eastern')
    
    def test_set_timezone_invalid_fallback(self):
        """Test setting invalid timezone falls back to UTC"""
        timezone = self.timezone_manager.set_timezone('Invalid/Timezone')
        self.assertEqual(timezone, 'UTC')
    
    @patch.dict(os.environ, {'REGION_TZ': 'Europe/London'})
    def test_set_timezone_from_environment(self):
        """Test setting timezone from environment variable"""
        timezone = self.timezone_manager.set_timezone()
        self.assertEqual(timezone, 'Europe/London')
    
    def test_set_timezone_default_utc(self):
        """Test default timezone is UTC"""
        with patch.dict(os.environ, {}, clear=True):
            timezone = self.timezone_manager.set_timezone()
            self.assertEqual(timezone, 'UTC')


class TestEC2Manager(unittest.TestCase):
    """Test EC2Manager functionality"""
    
    def setUp(self):
        """Set up test environment"""
        with patch('boto3.client'), patch('boto3.resource'):
            self.ec2_manager = EC2Manager('us-east-1')
    
    def test_validate_time_format_valid(self):
        """Test time format validation for valid times"""
        valid_times = ['00:00', '09:30', '12:00', '18:45', '23:59']
        
        for time_str in valid_times:
            with self.subTest(time=time_str):
                self.assertTrue(self.ec2_manager._validate_time_format(time_str))
    
    def test_validate_time_format_invalid(self):
        """Test time format validation for invalid times"""
        invalid_times = ['24:00', '12:60', '9:30', '12:5', 'invalid', '']
        
        for time_str in invalid_times:
            with self.subTest(time=time_str):
                self.assertFalse(self.ec2_manager._validate_time_format(time_str))
    
    def test_create_ec2_resource(self):
        """Test creating EC2Resource from AWS API response"""
        instance_data = {
            'InstanceId': 'i-1234567890abcdef0',
            'State': {'Name': 'running'},
            'InstanceType': 't3.micro',
            'Placement': {'AvailabilityZone': 'us-east-1a'},
            'Tags': [
                {'Key': 'Name', 'Value': 'TestInstance'},
                {'Key': 'AutoStart', 'Value': 'true'}
            ],
            'PrivateIpAddress': '10.0.1.100',
            'PublicIpAddress': '54.123.45.67'
        }
        
        resource = self.ec2_manager._create_ec2_resource(instance_data)
        
        self.assertEqual(resource.instance_id, 'i-1234567890abcdef0')
        self.assertEqual(resource.state, 'running')
        self.assertEqual(resource.instance_type, 't3.micro')
        self.assertEqual(resource.availability_zone, 'us-east-1a')
        self.assertEqual(resource.tags['Name'], 'TestInstance')
        self.assertEqual(resource.tags['AutoStart'], 'true')
        self.assertEqual(resource.private_ip, '10.0.1.100')
        self.assertEqual(resource.public_ip, '54.123.45.67')
    
    @patch('boto3.client')
    def test_get_instances_by_tag(self, mock_boto_client):
        """Test getting instances by tag"""
        # Mock EC2 client response
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_paginator = Mock()
        mock_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'Reservations': [
                    {
                        'Instances': [
                            {
                                'InstanceId': 'i-1234567890abcdef0',
                                'State': {'Name': 'stopped'},
                                'InstanceType': 't3.micro',
                                'Placement': {'AvailabilityZone': 'us-east-1a'},
                                'Tags': [{'Key': 'AutoStart', 'Value': 'true'}]
                            }
                        ]
                    }
                ]
            }
        ]
        
        # Reinitialize manager with mocked client
        with patch('boto3.resource'):
            ec2_manager = EC2Manager('us-east-1')
        
        instances = ec2_manager.get_instances_by_tag(
            tag_name='AutoStart',
            tag_values=['true'],
            instance_states=['stopped']
        )
        
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].instance_id, 'i-1234567890abcdef0')
        self.assertEqual(instances[0].state, 'stopped')
    
    def test_start_single_instance_success(self):
        """Test starting a single instance successfully"""
        # Create a test instance
        instance = EC2Resource(
            instance_id='i-1234567890abcdef0',
            state='stopped',
            instance_type='t3.micro',
            availability_zone='us-east-1a',
            tags={'AutoStart': 'true'}
        )
        
        # Mock successful start response
        self.ec2_manager.ec2_client.start_instances.return_value = {
            'StartingInstances': [
                {
                    'InstanceId': 'i-1234567890abcdef0',
                    'CurrentState': {'Name': 'pending'},
                    'PreviousState': {'Name': 'stopped'}
                }
            ]
        }
        
        result = self.ec2_manager._start_single_instance(instance)
        
        self.assertTrue(result.success)
        self.assertEqual(result.instance_id, 'i-1234567890abcdef0')
        self.assertEqual(result.action, 'start')
        self.assertIn('pending', result.message)
    
    def test_start_single_instance_wrong_state(self):
        """Test starting instance in wrong state"""
        # Create a test instance in running state
        instance = EC2Resource(
            instance_id='i-1234567890abcdef0',
            state='running',
            instance_type='t3.micro',
            availability_zone='us-east-1a',
            tags={'AutoStart': 'true'}
        )
        
        result = self.ec2_manager._start_single_instance(instance)
        
        self.assertFalse(result.success)
        self.assertEqual(result.instance_id, 'i-1234567890abcdef0')
        self.assertIn('not in stopped state', result.message)
    
    def test_stop_single_instance_success(self):
        """Test stopping a single instance successfully"""
        # Create a test instance
        instance = EC2Resource(
            instance_id='i-1234567890abcdef0',
            state='running',
            instance_type='t3.micro',
            availability_zone='us-east-1a',
            tags={'AutoStop': 'true'}
        )
        
        # Mock successful stop response
        self.ec2_manager.ec2_client.stop_instances.return_value = {
            'StoppingInstances': [
                {
                    'InstanceId': 'i-1234567890abcdef0',
                    'CurrentState': {'Name': 'stopping'},
                    'PreviousState': {'Name': 'running'}
                }
            ]
        }
        
        result = self.ec2_manager._stop_single_instance(instance)
        
        self.assertTrue(result.success)
        self.assertEqual(result.instance_id, 'i-1234567890abcdef0')
        self.assertEqual(result.action, 'stop')
        self.assertIn('stopping', result.message)


class TestLambdaResponse(unittest.TestCase):
    """Test Lambda response creation"""
    
    def test_create_lambda_response_success(self):
        """Test creating successful Lambda response"""
        results = [
            OperationResult(
                success=True,
                instance_id='i-1234567890abcdef0',
                action='start',
                message='Started successfully'
            )
        ]
        
        response = create_lambda_response(
            status_code=200,
            results=results,
            action='auto_start'
        )
        
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('application/json', response['headers']['Content-Type'])
        
        body = json.loads(response['body'])
        self.assertEqual(body['action'], 'auto_start')
        self.assertEqual(body['summary']['total_processed'], 1)
        self.assertEqual(body['summary']['successful'], 1)
        self.assertEqual(body['summary']['failed'], 0)
    
    def test_create_lambda_response_with_failures(self):
        """Test creating Lambda response with failures"""
        results = [
            OperationResult(
                success=True,
                instance_id='i-1234567890abcdef0',
                action='start',
                message='Started successfully'
            ),
            OperationResult(
                success=False,
                instance_id='i-0987654321fedcba0',
                action='start',
                message='Failed to start',
                error_code='InvalidInstanceState'
            )
        ]
        
        response = create_lambda_response(
            status_code=207,
            results=results,
            action='auto_start'
        )
        
        self.assertEqual(response['statusCode'], 207)
        
        body = json.loads(response['body'])
        self.assertEqual(body['summary']['total_processed'], 2)
        self.assertEqual(body['summary']['successful'], 1)
        self.assertEqual(body['summary']['failed'], 1)


class TestIntegration(unittest.TestCase):
    """Integration tests for EC2 utilities"""
    
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_full_workflow_start_instances(self, mock_resource, mock_client):
        """Test full workflow for starting instances"""
        # Mock EC2 client
        mock_ec2_client = Mock()
        mock_client.return_value = mock_ec2_client
        
        # Mock paginator for describe_instances
        mock_paginator = Mock()
        mock_ec2_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'Reservations': [
                    {
                        'Instances': [
                            {
                                'InstanceId': 'i-1234567890abcdef0',
                                'State': {'Name': 'stopped'},
                                'InstanceType': 't3.micro',
                                'Placement': {'AvailabilityZone': 'us-east-1a'},
                                'Tags': [{'Key': 'AutoStart', 'Value': 'true'}]
                            }
                        ]
                    }
                ]
            }
        ]
        
        # Mock start_instances response
        mock_ec2_client.start_instances.return_value = {
            'StartingInstances': [
                {
                    'InstanceId': 'i-1234567890abcdef0',
                    'CurrentState': {'Name': 'pending'},
                    'PreviousState': {'Name': 'stopped'}
                }
            ]
        }
        
        # Create EC2Manager and test workflow
        ec2_manager = EC2Manager('us-east-1')
        
        # Get instances by tag
        instances = ec2_manager.get_instances_by_tag(
            tag_name='AutoStart',
            tag_values=['true'],
            instance_states=['stopped']
        )
        
        self.assertEqual(len(instances), 1)
        
        # Start instances
        results = ec2_manager.start_instances(instances)
        
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        
        # Verify start_instances was called
        mock_ec2_client.start_instances.assert_called_once_with(
            InstanceIds=['i-1234567890abcdef0']
        )


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios"""
    
    def setUp(self):
        """Set up test environment"""
        with patch('boto3.client'), patch('boto3.resource'):
            self.ec2_manager = EC2Manager('us-east-1')
    
    def test_client_error_handling(self):
        """Test handling of AWS ClientError"""
        from botocore.exceptions import ClientError
        
        instance = EC2Resource(
            instance_id='i-1234567890abcdef0',
            state='stopped',
            instance_type='t3.micro',
            availability_zone='us-east-1a',
            tags={'AutoStart': 'true'}
        )
        
        # Mock ClientError
        error_response = {
            'Error': {
                'Code': 'InvalidInstanceID.NotFound',
                'Message': 'The instance ID does not exist'
            }
        }
        self.ec2_manager.ec2_client.start_instances.side_effect = ClientError(
            error_response, 'StartInstances'
        )
        
        result = self.ec2_manager._start_single_instance(instance)
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, 'InvalidInstanceID.NotFound')
        self.assertIn('does not exist', result.message)


if __name__ == '__main__':
    # Configure logging for tests
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Run tests
    unittest.main(verbosity=2)
