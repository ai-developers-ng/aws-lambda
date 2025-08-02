"""
Comprehensive test suite for unified database password rotation.
Tests all rotation steps, database engines, and error conditions.
"""

import json
import os
import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock, call
from moto import mock_secretsmanager, mock_cloudwatch
import boto3

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lambda_function import (
    lambda_handler, create_secret, set_secret, test_secret, finish_secret,
    _generate_secure_password, _validate_rotation_request,
    RotationError, DatabaseConnectionError, PasswordGenerationError
)

class TestPasswordRotation(unittest.TestCase):
    """Test cases for password rotation functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.secret_arn = "arn:aws:secretsmanager:us-west-2:123456789012:secret:test-secret-abc123"
        self.token = "test-token-12345"
        
        self.test_secret = {
            "engine": "postgresql",
            "host": "test-db.example.com",
            "port": "5432",
            "username": "testuser",
            "password": "oldpassword",
            "dbname": "testdb"
        }
        
        # Mock logger
        self.mock_logger = Mock()
        
        # Set environment variables
        os.environ.update({
            'LOG_LEVEL': 'DEBUG',
            'MAX_RETRIES': '3',
            'CONNECTION_TIMEOUT': '30',
            'PASSWORD_LENGTH': '32',
            'PASSWORD_COMPLEXITY': 'high'
        })
    
    def tearDown(self):
        """Clean up after tests."""
        # Clean up environment variables
        env_vars = ['LOG_LEVEL', 'MAX_RETRIES', 'CONNECTION_TIMEOUT', 
                   'PASSWORD_LENGTH', 'PASSWORD_COMPLEXITY']
        for var in env_vars:
            os.environ.pop(var, None)

class TestLambdaHandler(TestPasswordRotation):
    """Test the main Lambda handler function."""
    
    @patch('lambda_function._validate_rotation_request')
    @patch('lambda_function.create_secret')
    @patch('lambda_function._send_metric')
    def test_lambda_handler_create_secret(self, mock_send_metric, mock_create, mock_validate):
        """Test Lambda handler for createSecret step."""
        event = {
            'SecretId': self.secret_arn,
            'ClientRequestToken': self.token,
            'Step': 'createSecret'
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['statusCode'], 200)
        mock_validate.assert_called_once()
        mock_create.assert_called_once()
        mock_send_metric.assert_called_with('RotationSuccess', 1, 'createSecret', unittest.mock.ANY)
    
    @patch('lambda_function._validate_rotation_request')
    @patch('lambda_function.set_secret')
    @patch('lambda_function._send_metric')
    def test_lambda_handler_set_secret(self, mock_send_metric, mock_set, mock_validate):
        """Test Lambda handler for setSecret step."""
        event = {
            'SecretId': self.secret_arn,
            'ClientRequestToken': self.token,
            'Step': 'setSecret'
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['statusCode'], 200)
        mock_validate.assert_called_once()
        mock_set.assert_called_once()
        mock_send_metric.assert_called_with('RotationSuccess', 1, 'setSecret', unittest.mock.ANY)
    
    @patch('lambda_function._validate_rotation_request')
    @patch('lambda_function.test_secret')
    @patch('lambda_function._send_metric')
    def test_lambda_handler_test_secret(self, mock_send_metric, mock_test, mock_validate):
        """Test Lambda handler for testSecret step."""
        event = {
            'SecretId': self.secret_arn,
            'ClientRequestToken': self.token,
            'Step': 'testSecret'
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['statusCode'], 200)
        mock_validate.assert_called_once()
        mock_test.assert_called_once()
        mock_send_metric.assert_called_with('RotationSuccess', 1, 'testSecret', unittest.mock.ANY)
    
    @patch('lambda_function._validate_rotation_request')
    @patch('lambda_function.finish_secret')
    @patch('lambda_function._send_metric')
    def test_lambda_handler_finish_secret(self, mock_send_metric, mock_finish, mock_validate):
        """Test Lambda handler for finishSecret step."""
        event = {
            'SecretId': self.secret_arn,
            'ClientRequestToken': self.token,
            'Step': 'finishSecret'
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        self.assertEqual(result['statusCode'], 200)
        mock_validate.assert_called_once()
        mock_finish.assert_called_once()
        mock_send_metric.assert_called_with('RotationSuccess', 1, 'finishSecret', unittest.mock.ANY)
    
    def test_lambda_handler_missing_parameters(self):
        """Test Lambda handler with missing parameters."""
        event = {
            'SecretId': self.secret_arn,
            # Missing ClientRequestToken and Step
        }
        context = Mock()
        
        with self.assertRaises(RotationError):
            lambda_handler(event, context)
    
    def test_lambda_handler_invalid_step(self):
        """Test Lambda handler with invalid step."""
        event = {
            'SecretId': self.secret_arn,
            'ClientRequestToken': self.token,
            'Step': 'invalidStep'
        }
        context = Mock()
        
        with patch('lambda_function._validate_rotation_request'):
            with self.assertRaises(RotationError):
                lambda_handler(event, context)

class TestPasswordGeneration(TestPasswordRotation):
    """Test password generation functionality."""
    
    def test_generate_secure_password_high_complexity(self):
        """Test high complexity password generation."""
        os.environ['PASSWORD_COMPLEXITY'] = 'high'
        os.environ['PASSWORD_LENGTH'] = '32'
        
        password = _generate_secure_password(self.mock_logger)
        
        self.assertEqual(len(password), 32)
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
        self.assertTrue(any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password))
    
    def test_generate_secure_password_medium_complexity(self):
        """Test medium complexity password generation."""
        os.environ['PASSWORD_COMPLEXITY'] = 'medium'
        os.environ['PASSWORD_LENGTH'] = '24'
        
        password = _generate_secure_password(self.mock_logger)
        
        self.assertEqual(len(password), 24)
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))
    
    def test_generate_secure_password_low_complexity(self):
        """Test low complexity password generation."""
        os.environ['PASSWORD_COMPLEXITY'] = 'low'
        os.environ['PASSWORD_LENGTH'] = '16'
        
        password = _generate_secure_password(self.mock_logger)
        
        self.assertEqual(len(password), 16)
        self.assertTrue(any(c.isupper() for c in password))
        self.assertTrue(any(c.islower() for c in password))
        self.assertTrue(any(c.isdigit() for c in password))

class TestCreateSecret(TestPasswordRotation):
    """Test create secret functionality."""
    
    @patch('lambda_function.secretsmanager')
    @patch('lambda_function._generate_secure_password')
    def test_create_secret_success(self, mock_generate_password, mock_sm):
        """Test successful secret creation."""
        mock_generate_password.return_value = "newpassword123!"
        
        # Mock existing secret version check (should raise ResourceNotFoundException)
        mock_sm.get_secret_value.side_effect = [
            Exception("ResourceNotFoundException"),  # First call for version check
            {'SecretString': json.dumps(self.test_secret)}  # Second call for current secret
        ]
        
        create_secret(self.secret_arn, self.token, self.mock_logger)
        
        # Verify put_secret_value was called with new password
        mock_sm.put_secret_value.assert_called_once()
        call_args = mock_sm.put_secret_value.call_args
        secret_string = json.loads(call_args[1]['SecretString'])
        self.assertEqual(secret_string['password'], "newpassword123!")
    
    @patch('lambda_function.secretsmanager')
    def test_create_secret_already_exists(self, mock_sm):
        """Test create secret when version already exists."""
        # Mock existing secret version
        mock_sm.get_secret_value.return_value = {
            'SecretString': json.dumps(self.test_secret)
        }
        
        create_secret(self.secret_arn, self.token, self.mock_logger)
        
        # Verify put_secret_value was not called
        mock_sm.put_secret_value.assert_not_called()

class TestSetSecret(TestPasswordRotation):
    """Test set secret functionality."""
    
    @patch('lambda_function.secretsmanager')
    @patch('lambda_function._rotate_postgresql_password')
    def test_set_secret_postgresql(self, mock_rotate, mock_sm):
        """Test set secret for PostgreSQL."""
        pending_secret = self.test_secret.copy()
        pending_secret['password'] = 'newpassword123!'
        
        mock_sm.get_secret_value.side_effect = [
            {'SecretString': json.dumps(pending_secret)},  # Pending secret
            {'SecretString': json.dumps(self.test_secret)}  # Current secret
        ]
        
        set_secret(self.secret_arn, self.token, self.mock_logger)
        
        mock_rotate.assert_called_once_with(self.test_secret, pending_secret, self.mock_logger)
    
    @patch('lambda_function.secretsmanager')
    @patch('lambda_function._rotate_mysql_password')
    def test_set_secret_mysql(self, mock_rotate, mock_sm):
        """Test set secret for MySQL."""
        mysql_secret = self.test_secret.copy()
        mysql_secret['engine'] = 'mysql'
        pending_secret = mysql_secret.copy()
        pending_secret['password'] = 'newpassword123!'
        
        mock_sm.get_secret_value.side_effect = [
            {'SecretString': json.dumps(pending_secret)},
            {'SecretString': json.dumps(mysql_secret)}
        ]
        
        set_secret(self.secret_arn, self.token, self.mock_logger)
        
        mock_rotate.assert_called_once_with(mysql_secret, pending_secret, self.mock_logger)
    
    @patch('lambda_function.secretsmanager')
    def test_set_secret_unsupported_engine(self, mock_sm):
        """Test set secret with unsupported engine."""
        unsupported_secret = self.test_secret.copy()
        unsupported_secret['engine'] = 'unsupported'
        
        mock_sm.get_secret_value.side_effect = [
            {'SecretString': json.dumps(unsupported_secret)},
            {'SecretString': json.dumps(unsupported_secret)}
        ]
        
        with self.assertRaises(RotationError):
            set_secret(self.secret_arn, self.token, self.mock_logger)
    
    @patch('lambda_function.secretsmanager')
    def test_set_secret_missing_fields(self, mock_sm):
        """Test set secret with missing required fields."""
        incomplete_secret = {'engine': 'postgresql', 'host': 'test.com'}
        
        mock_sm.get_secret_value.side_effect = [
            {'SecretString': json.dumps(incomplete_secret)},
            {'SecretString': json.dumps(incomplete_secret)}
        ]
        
        with self.assertRaises(RotationError):
            set_secret(self.secret_arn, self.token, self.mock_logger)

class TestTestSecret(TestPasswordRotation):
    """Test test secret functionality."""
    
    @patch('lambda_function.secretsmanager')
    @patch('lambda_function._test_postgresql_connection')
    def test_test_secret_postgresql(self, mock_test, mock_sm):
        """Test secret testing for PostgreSQL."""
        mock_sm.get_secret_value.return_value = {
            'SecretString': json.dumps(self.test_secret)
        }
        
        test_secret(self.secret_arn, self.token, self.mock_logger)
        
        mock_test.assert_called_once_with(self.test_secret, self.mock_logger)
    
    @patch('lambda_function.secretsmanager')
    @patch('lambda_function._test_mysql_connection')
    def test_test_secret_mysql(self, mock_test, mock_sm):
        """Test secret testing for MySQL."""
        mysql_secret = self.test_secret.copy()
        mysql_secret['engine'] = 'mysql'
        
        mock_sm.get_secret_value.return_value = {
            'SecretString': json.dumps(mysql_secret)
        }
        
        test_secret(self.secret_arn, self.token, self.mock_logger)
        
        mock_test.assert_called_once_with(mysql_secret, self.mock_logger)

class TestFinishSecret(TestPasswordRotation):
    """Test finish secret functionality."""
    
    @patch('lambda_function.secretsmanager')
    def test_finish_secret_success(self, mock_sm):
        """Test successful secret finishing."""
        mock_sm.describe_secret.return_value = {
            'VersionIdsToStages': {
                'old-version': ['AWSCURRENT'],
                self.token: ['AWSPENDING']
            }
        }
        
        finish_secret(self.secret_arn, self.token, self.mock_logger)
        
        mock_sm.update_secret_version_stage.assert_called_once_with(
            SecretId=self.secret_arn,
            VersionStage='AWSCURRENT',
            MoveToVersionId=self.token,
            RemoveFromVersionId='old-version'
        )
    
    @patch('lambda_function.secretsmanager')
    def test_finish_secret_already_current(self, mock_sm):
        """Test finish secret when version is already current."""
        mock_sm.describe_secret.return_value = {
            'VersionIdsToStages': {
                self.token: ['AWSCURRENT']
            }
        }
        
        finish_secret(self.secret_arn, self.token, self.mock_logger)
        
        mock_sm.update_secret_version_stage.assert_not_called()

class TestDatabaseConnections(TestPasswordRotation):
    """Test database connection functionality."""
    
    @patch('lambda_function.psycopg2')
    def test_postgresql_connection_context_manager(self, mock_psycopg2):
        """Test PostgreSQL connection context manager."""
        mock_conn = Mock()
        mock_psycopg2.connect.return_value = mock_conn
        
        from lambda_function import _get_postgresql_connection
        
        with _get_postgresql_connection(self.test_secret, self.mock_logger) as conn:
            self.assertEqual(conn, mock_conn)
        
        mock_conn.close.assert_called_once()
    
    @patch('lambda_function.pymysql')
    def test_mysql_connection_context_manager(self, mock_pymysql):
        """Test MySQL connection context manager."""
        mock_conn = Mock()
        mock_pymysql.connect.return_value = mock_conn
        
        from lambda_function import _get_mysql_connection
        
        with _get_mysql_connection(self.test_secret, self.mock_logger) as conn:
            self.assertEqual(conn, mock_conn)
        
        mock_conn.close.assert_called_once()
    
    @patch('lambda_function.cx_Oracle')
    def test_oracle_connection_context_manager(self, mock_oracle):
        """Test Oracle connection context manager."""
        mock_conn = Mock()
        mock_oracle.connect.return_value = mock_conn
        mock_oracle.makedsn.return_value = "test-dsn"
        
        from lambda_function import _get_oracle_connection
        
        oracle_secret = self.test_secret.copy()
        oracle_secret['engine'] = 'oracle'
        oracle_secret['sid'] = 'ORCL'
        
        with _get_oracle_connection(oracle_secret, self.mock_logger) as conn:
            self.assertEqual(conn, mock_conn)
        
        mock_conn.close.assert_called_once()

class TestValidation(TestPasswordRotation):
    """Test validation functionality."""
    
    @patch('lambda_function.secretsmanager')
    def test_validate_rotation_request_success(self, mock_sm):
        """Test successful rotation request validation."""
        mock_sm.describe_secret.return_value = {
            'RotationEnabled': True,
            'VersionIdsToStages': {
                self.token: ['AWSPENDING']
            }
        }
        
        # Should not raise exception
        _validate_rotation_request(self.secret_arn, self.token, self.mock_logger)
    
    @patch('lambda_function.secretsmanager')
    def test_validate_rotation_request_not_enabled(self, mock_sm):
        """Test validation with rotation not enabled."""
        mock_sm.describe_secret.return_value = {
            'RotationEnabled': False
        }
        
        with self.assertRaises(RotationError):
            _validate_rotation_request(self.secret_arn, self.token, self.mock_logger)
    
    @patch('lambda_function.secretsmanager')
    def test_validate_rotation_request_invalid_token(self, mock_sm):
        """Test validation with invalid token."""
        mock_sm.describe_secret.return_value = {
            'RotationEnabled': True,
            'VersionIdsToStages': {
                'other-token': ['AWSPENDING']
            }
        }
        
        with self.assertRaises(RotationError):
            _validate_rotation_request(self.secret_arn, self.token, self.mock_logger)

class TestErrorHandling(TestPasswordRotation):
    """Test error handling scenarios."""
    
    def test_rotation_error_inheritance(self):
        """Test custom exception inheritance."""
        error = RotationError("Test error")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Test error")
    
    def test_database_connection_error_inheritance(self):
        """Test database connection error inheritance."""
        error = DatabaseConnectionError("Connection failed")
        self.assertIsInstance(error, RotationError)
        self.assertEqual(str(error), "Connection failed")
    
    def test_password_generation_error_inheritance(self):
        """Test password generation error inheritance."""
        error = PasswordGenerationError("Generation failed")
        self.assertIsInstance(error, RotationError)
        self.assertEqual(str(error), "Generation failed")

class TestIntegration(TestPasswordRotation):
    """Integration tests for complete rotation workflow."""
    
    @mock_secretsmanager
    @patch('lambda_function._rotate_postgresql_password')
    @patch('lambda_function._test_postgresql_connection')
    def test_complete_rotation_workflow(self, mock_test, mock_rotate):
        """Test complete rotation workflow from start to finish."""
        # Set up mocked Secrets Manager
        client = boto3.client('secretsmanager', region_name='us-west-2')
        
        # Create initial secret
        secret_name = 'test-db-secret'
        client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(self.test_secret)
        )
        
        secret_arn = f"arn:aws:secretsmanager:us-west-2:123456789012:secret:{secret_name}-abc123"
        
        # Enable rotation
        client.update_secret(
            SecretId=secret_name,
            Description="Test secret for rotation"
        )
        
        # Test each step of rotation
        context = Mock()
        
        # Step 1: Create secret
        event = {
            'SecretId': secret_arn,
            'ClientRequestToken': self.token,
            'Step': 'createSecret'
        }
        
        with patch('lambda_function.secretsmanager', client):
            result = lambda_handler(event, context)
            self.assertEqual(result['statusCode'], 200)
        
        # Step 2: Set secret
        event['Step'] = 'setSecret'
        with patch('lambda_function.secretsmanager', client):
            result = lambda_handler(event, context)
            self.assertEqual(result['statusCode'], 200)
        
        # Step 3: Test secret
        event['Step'] = 'testSecret'
        with patch('lambda_function.secretsmanager', client):
            result = lambda_handler(event, context)
            self.assertEqual(result['statusCode'], 200)
        
        # Step 4: Finish secret
        event['Step'] = 'finishSecret'
        with patch('lambda_function.secretsmanager', client):
            result = lambda_handler(event, context)
            self.assertEqual(result['statusCode'], 200)

if __name__ == '__main__':
    # Set up test environment
    os.environ.update({
        'AWS_DEFAULT_REGION': 'us-west-2',
        'LOG_LEVEL': 'DEBUG'
    })
    
    # Run tests
    unittest.main(verbosity=2)
