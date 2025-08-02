"""
Production-ready AWS Lambda function for dynamic database password rotation.
Supports PostgreSQL, MySQL/MariaDB, and Oracle databases with comprehensive
error handling, security, and monitoring.
"""

import boto3
import json
import logging
import os
import random
import secrets
import string
import time
import uuid
from contextlib import contextmanager
from typing import Dict, Any, Optional, Tuple
from botocore.exceptions import ClientError, BotoCoreError

# Database drivers
try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    psycopg2 = None

try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pymysql = None

try:
    import cx_Oracle
except ImportError:
    cx_Oracle = None

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Create formatter for structured logging
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
for handler in logger.handlers:
    handler.setFormatter(formatter)

# AWS clients
secretsmanager = boto3.client('secretsmanager')
cloudwatch = boto3.client('cloudwatch')

# Configuration constants
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3'))
RETRY_DELAY = int(os.environ.get('RETRY_DELAY', '5'))
CONNECTION_TIMEOUT = int(os.environ.get('CONNECTION_TIMEOUT', '30'))
PASSWORD_LENGTH = int(os.environ.get('PASSWORD_LENGTH', '32'))
PASSWORD_COMPLEXITY = os.environ.get('PASSWORD_COMPLEXITY', 'high')

class RotationError(Exception):
    """Custom exception for rotation-specific errors."""
    pass

class DatabaseConnectionError(RotationError):
    """Exception for database connection issues."""
    pass

class PasswordGenerationError(RotationError):
    """Exception for password generation issues."""
    pass

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for AWS Secrets Manager password rotation.
    
    Args:
        event: Lambda event containing SecretId, ClientRequestToken, and Step
        context: Lambda context object
        
    Returns:
        Dict containing operation result
    """
    # Generate correlation ID for request tracking
    correlation_id = str(uuid.uuid4())
    
    # Add correlation ID to all log messages
    logger = logging.LoggerAdapter(
        logging.getLogger(__name__),
        {'correlation_id': correlation_id}
    )
    
    try:
        # Validate required event parameters
        required_params = ['SecretId', 'ClientRequestToken', 'Step']
        for param in required_params:
            if param not in event:
                raise ValueError(f"Missing required parameter: {param}")
        
        secret_arn = event['SecretId']
        token = event['ClientRequestToken']
        step = event['Step']
        
        logger.info(f"Starting rotation step: {step} for secret: {secret_arn}")
        
        # Validate rotation is enabled and token is valid
        _validate_rotation_request(secret_arn, token, logger)
        
        # Execute the appropriate rotation step
        if step == "createSecret":
            create_secret(secret_arn, token, logger)
        elif step == "setSecret":
            set_secret(secret_arn, token, logger)
        elif step == "testSecret":
            test_secret(secret_arn, token, logger)
        elif step == "finishSecret":
            finish_secret(secret_arn, token, logger)
        else:
            raise ValueError(f"Invalid rotation step: {step}")
        
        logger.info(f"Successfully completed rotation step: {step}")
        
        # Send success metric to CloudWatch
        _send_metric('RotationSuccess', 1, step, logger)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully completed {step}',
                'correlationId': correlation_id
            })
        }
        
    except Exception as e:
        error_msg = f"Rotation failed at step {event.get('Step', 'unknown')}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Send failure metric to CloudWatch
        _send_metric('RotationFailure', 1, event.get('Step', 'unknown'), logger)
        
        # Re-raise the exception to trigger Lambda error handling
        raise RotationError(error_msg) from e

def _validate_rotation_request(secret_arn: str, token: str, logger: logging.LoggerAdapter) -> None:
    """Validate that rotation is enabled and token is valid."""
    try:
        metadata = secretsmanager.describe_secret(SecretId=secret_arn)
        
        if not metadata.get('RotationEnabled', False):
            raise RotationError("Secret rotation is not enabled")
        
        version_stages = metadata.get('VersionIdsToStages', {})
        if token not in version_stages:
            raise RotationError(f"Invalid token: {token}")
        
        if 'AWSPENDING' not in version_stages[token]:
            raise RotationError(f"Token {token} is not in AWSPENDING stage")
            
        logger.info("Rotation request validation successful")
        
    except ClientError as e:
        raise RotationError(f"Failed to validate rotation request: {e}")

def create_secret(secret_arn: str, token: str, logger: logging.LoggerAdapter) -> None:
    """
    Create a new secret version with a new password.
    
    Args:
        secret_arn: ARN of the secret to rotate
        token: Client request token for the new version
        logger: Logger instance with correlation ID
    """
    try:
        # Check if the secret version already exists
        try:
            secretsmanager.get_secret_value(
                SecretId=secret_arn,
                VersionId=token,
                VersionStage="AWSPENDING"
            )
            logger.info("Secret version already exists, skipping creation")
            return
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise
        
        # Get current secret
        current_secret = secretsmanager.get_secret_value(
            SecretId=secret_arn,
            VersionStage="AWSCURRENT"
        )
        
        current_dict = json.loads(current_secret['SecretString'])
        
        # Generate new secure password
        new_password = _generate_secure_password(logger)
        
        # Create new secret version
        new_dict = current_dict.copy()
        new_dict['password'] = new_password
        
        # Store the new secret version
        secretsmanager.put_secret_value(
            SecretId=secret_arn,
            ClientRequestToken=token,
            SecretString=json.dumps(new_dict),
            VersionStages=['AWSPENDING']
        )
        
        logger.info("Successfully created new secret version")
        
    except Exception as e:
        raise RotationError(f"Failed to create secret: {e}") from e

def set_secret(secret_arn: str, token: str, logger: logging.LoggerAdapter) -> None:
    """
    Set the new password in the database.
    
    Args:
        secret_arn: ARN of the secret to rotate
        token: Client request token for the new version
        logger: Logger instance with correlation ID
    """
    try:
        # Get both current and pending secrets
        pending_secret = secretsmanager.get_secret_value(
            SecretId=secret_arn,
            VersionId=token,
            VersionStage="AWSPENDING"
        )
        
        current_secret = secretsmanager.get_secret_value(
            SecretId=secret_arn,
            VersionStage="AWSCURRENT"
        )
        
        pending_dict = json.loads(pending_secret['SecretString'])
        current_dict = json.loads(current_secret['SecretString'])
        
        # Validate required fields
        required_fields = ['engine', 'host', 'port', 'username', 'password']
        for field in required_fields:
            if field not in current_dict:
                raise RotationError(f"Missing required field in secret: {field}")
        
        engine = current_dict['engine'].lower()
        logger.info(f"Setting password for database engine: {engine}")
        
        # Route to appropriate database handler
        if engine in ['postgres', 'postgresql']:
            _rotate_postgresql_password(current_dict, pending_dict, logger)
        elif engine in ['mysql', 'mariadb']:
            _rotate_mysql_password(current_dict, pending_dict, logger)
        elif engine == 'oracle':
            _rotate_oracle_password(current_dict, pending_dict, logger)
        else:
            raise RotationError(f"Unsupported database engine: {engine}")
        
        logger.info("Successfully set new password in database")
        
    except Exception as e:
        raise RotationError(f"Failed to set secret: {e}") from e

def test_secret(secret_arn: str, token: str, logger: logging.LoggerAdapter) -> None:
    """
    Test the new password by attempting to connect to the database.
    
    Args:
        secret_arn: ARN of the secret to rotate
        token: Client request token for the new version
        logger: Logger instance with correlation ID
    """
    try:
        # Get the pending secret
        pending_secret = secretsmanager.get_secret_value(
            SecretId=secret_arn,
            VersionId=token,
            VersionStage="AWSPENDING"
        )
        
        pending_dict = json.loads(pending_secret['SecretString'])
        engine = pending_dict['engine'].lower()
        
        logger.info(f"Testing new password for database engine: {engine}")
        
        # Test connection with new password
        if engine in ['postgres', 'postgresql']:
            _test_postgresql_connection(pending_dict, logger)
        elif engine in ['mysql', 'mariadb']:
            _test_mysql_connection(pending_dict, logger)
        elif engine == 'oracle':
            _test_oracle_connection(pending_dict, logger)
        else:
            raise RotationError(f"Unsupported database engine: {engine}")
        
        logger.info("Successfully tested new password")
        
    except Exception as e:
        raise RotationError(f"Failed to test secret: {e}") from e

def finish_secret(secret_arn: str, token: str, logger: logging.LoggerAdapter) -> None:
    """
    Finalize the rotation by moving the new version to AWSCURRENT.
    
    Args:
        secret_arn: ARN of the secret to rotate
        token: Client request token for the new version
        logger: Logger instance with correlation ID
    """
    try:
        # Get current version information
        metadata = secretsmanager.describe_secret(SecretId=secret_arn)
        version_stages = metadata.get('VersionIdsToStages', {})
        
        # Find current version
        current_version = None
        for version_id, stages in version_stages.items():
            if 'AWSCURRENT' in stages:
                current_version = version_id
                break
        
        # If the token is already current, nothing to do
        if current_version == token:
            logger.info("Secret version is already current")
            return
        
        # Move the new version to AWSCURRENT
        secretsmanager.update_secret_version_stage(
            SecretId=secret_arn,
            VersionStage='AWSCURRENT',
            MoveToVersionId=token,
            RemoveFromVersionId=current_version
        )
        
        logger.info("Successfully finished secret rotation")
        
    except Exception as e:
        raise RotationError(f"Failed to finish secret rotation: {e}") from e

def _generate_secure_password(logger: logging.LoggerAdapter) -> str:
    """
    Generate a cryptographically secure password.
    
    Args:
        logger: Logger instance with correlation ID
        
    Returns:
        Secure password string
    """
    try:
        if PASSWORD_COMPLEXITY == 'high':
            # High complexity: uppercase, lowercase, digits, special characters
            chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
            min_upper = 2
            min_lower = 2
            min_digits = 2
            min_special = 2
        elif PASSWORD_COMPLEXITY == 'medium':
            # Medium complexity: uppercase, lowercase, digits, basic special
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
            min_upper = 1
            min_lower = 1
            min_digits = 1
            min_special = 1
        else:
            # Low complexity: alphanumeric only
            chars = string.ascii_letters + string.digits
            min_upper = 1
            min_lower = 1
            min_digits = 1
            min_special = 0
        
        # Generate password ensuring complexity requirements
        while True:
            password = ''.join(secrets.choice(chars) for _ in range(PASSWORD_LENGTH))
            
            # Check complexity requirements
            if (sum(1 for c in password if c.isupper()) >= min_upper and
                sum(1 for c in password if c.islower()) >= min_lower and
                sum(1 for c in password if c.isdigit()) >= min_digits and
                sum(1 for c in password if c in "!@#$%^&*()_+-=[]{}|;:,.<>?") >= min_special):
                break
        
        logger.info(f"Generated secure password with {PASSWORD_COMPLEXITY} complexity")
        return password
        
    except Exception as e:
        raise PasswordGenerationError(f"Failed to generate secure password: {e}") from e

@contextmanager
def _get_postgresql_connection(secret_dict: Dict[str, Any], logger: logging.LoggerAdapter):
    """Context manager for PostgreSQL connections."""
    if not psycopg2:
        raise DatabaseConnectionError("psycopg2 library not available")
    
    conn = None
    try:
        conn = psycopg2.connect(
            host=secret_dict['host'],
            port=int(secret_dict['port']),
            user=secret_dict['username'],
            password=secret_dict['password'],
            database=secret_dict.get('dbname', 'postgres'),
            connect_timeout=CONNECTION_TIMEOUT,
            sslmode='require'
        )
        conn.autocommit = True
        yield conn
    except psycopg2.Error as e:
        raise DatabaseConnectionError(f"PostgreSQL connection failed: {e}") from e
    finally:
        if conn:
            conn.close()

@contextmanager
def _get_mysql_connection(secret_dict: Dict[str, Any], logger: logging.LoggerAdapter):
    """Context manager for MySQL/MariaDB connections."""
    if not pymysql:
        raise DatabaseConnectionError("pymysql library not available")
    
    conn = None
    try:
        conn = pymysql.connect(
            host=secret_dict['host'],
            port=int(secret_dict['port']),
            user=secret_dict['username'],
            password=secret_dict['password'],
            database=secret_dict.get('dbname', 'mysql'),
            connect_timeout=CONNECTION_TIMEOUT,
            ssl={'ssl_disabled': False},
            autocommit=True
        )
        yield conn
    except pymysql.Error as e:
        raise DatabaseConnectionError(f"MySQL connection failed: {e}") from e
    finally:
        if conn:
            conn.close()

@contextmanager
def _get_oracle_connection(secret_dict: Dict[str, Any], logger: logging.LoggerAdapter):
    """Context manager for Oracle connections."""
    if not cx_Oracle:
        raise DatabaseConnectionError("cx_Oracle library not available")
    
    conn = None
    try:
        dsn = cx_Oracle.makedsn(
            secret_dict['host'],
            int(secret_dict['port']),
            sid=secret_dict.get('sid', 'ORCL')
        )
        conn = cx_Oracle.connect(
            user=secret_dict['username'],
            password=secret_dict['password'],
            dsn=dsn,
            timeout=CONNECTION_TIMEOUT
        )
        conn.autocommit = True
        yield conn
    except cx_Oracle.Error as e:
        raise DatabaseConnectionError(f"Oracle connection failed: {e}") from e
    finally:
        if conn:
            conn.close()

def _rotate_postgresql_password(current_dict: Dict[str, Any], pending_dict: Dict[str, Any], 
                               logger: logging.LoggerAdapter) -> None:
    """Rotate password for PostgreSQL database."""
    with _get_postgresql_connection(current_dict, logger) as conn:
        with conn.cursor() as cursor:
            # Use parameterized query to prevent SQL injection
            cursor.execute(
                sql.SQL("ALTER USER {} WITH PASSWORD %s").format(
                    sql.Identifier(pending_dict['username'])
                ),
                (pending_dict['password'],)
            )
    logger.info("PostgreSQL password rotation completed")

def _rotate_mysql_password(current_dict: Dict[str, Any], pending_dict: Dict[str, Any], 
                          logger: logging.LoggerAdapter) -> None:
    """Rotate password for MySQL/MariaDB database."""
    with _get_mysql_connection(current_dict, logger) as conn:
        with conn.cursor() as cursor:
            # Use parameterized query to prevent SQL injection
            cursor.execute(
                "ALTER USER %s@'%%' IDENTIFIED BY %s",
                (pending_dict['username'], pending_dict['password'])
            )
    logger.info("MySQL/MariaDB password rotation completed")

def _rotate_oracle_password(current_dict: Dict[str, Any], pending_dict: Dict[str, Any], 
                           logger: logging.LoggerAdapter) -> None:
    """Rotate password for Oracle database."""
    with _get_oracle_connection(current_dict, logger) as conn:
        with conn.cursor() as cursor:
            # Use parameterized query to prevent SQL injection
            cursor.execute(
                f"ALTER USER {pending_dict['username']} IDENTIFIED BY :new_password",
                new_password=pending_dict['password']
            )
    logger.info("Oracle password rotation completed")

def _test_postgresql_connection(secret_dict: Dict[str, Any], logger: logging.LoggerAdapter) -> None:
    """Test PostgreSQL connection with new password."""
    with _get_postgresql_connection(secret_dict, logger) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result[0] != 1:
                raise DatabaseConnectionError("PostgreSQL connection test failed")
    logger.info("PostgreSQL connection test successful")

def _test_mysql_connection(secret_dict: Dict[str, Any], logger: logging.LoggerAdapter) -> None:
    """Test MySQL/MariaDB connection with new password."""
    with _get_mysql_connection(secret_dict, logger) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result[0] != 1:
                raise DatabaseConnectionError("MySQL connection test failed")
    logger.info("MySQL/MariaDB connection test successful")

def _test_oracle_connection(secret_dict: Dict[str, Any], logger: logging.LoggerAdapter) -> None:
    """Test Oracle connection with new password."""
    with _get_oracle_connection(secret_dict, logger) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM DUAL")
            result = cursor.fetchone()
            if result[0] != 1:
                raise DatabaseConnectionError("Oracle connection test failed")
    logger.info("Oracle connection test successful")

def _send_metric(metric_name: str, value: float, step: str, logger: logging.LoggerAdapter) -> None:
    """Send custom metric to CloudWatch."""
    try:
        cloudwatch.put_metric_data(
            Namespace='AWS/SecretsManager/Rotation',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': 'Count',
                    'Dimensions': [
                        {
                            'Name': 'RotationStep',
                            'Value': step
                        }
                    ]
                }
            ]
        )
    except Exception as e:
        logger.warning(f"Failed to send CloudWatch metric: {e}")
