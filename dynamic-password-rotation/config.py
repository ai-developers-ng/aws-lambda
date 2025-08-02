"""
Configuration management for unified database password rotation.
Provides environment-specific settings and validation.
"""

import os
from typing import Dict, Any, Optional
from enum import Enum

class Environment(Enum):
    """Supported deployment environments."""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"

class DatabaseEngine(Enum):
    """Supported database engines."""
    POSTGRESQL = "postgresql"
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    ORACLE = "oracle"

class PasswordComplexity(Enum):
    """Password complexity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Config:
    """Configuration class for password rotation settings."""
    
    def __init__(self, environment: Optional[str] = None):
        """
        Initialize configuration based on environment.
        
        Args:
            environment: Target environment (dev, staging, prod)
        """
        self.environment = Environment(environment or os.environ.get('ENVIRONMENT', 'dev'))
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration based on environment."""
        # Base configuration
        self.config = {
            'lambda': {
                'timeout': int(os.environ.get('LAMBDA_TIMEOUT', '300')),
                'memory_size': int(os.environ.get('LAMBDA_MEMORY_SIZE', '512')),
                'runtime': os.environ.get('LAMBDA_RUNTIME', 'python3.11'),
                'log_level': os.environ.get('LOG_LEVEL', 'INFO'),
            },
            'rotation': {
                'max_retries': int(os.environ.get('MAX_RETRIES', '3')),
                'retry_delay': int(os.environ.get('RETRY_DELAY', '5')),
                'connection_timeout': int(os.environ.get('CONNECTION_TIMEOUT', '30')),
                'password_length': int(os.environ.get('PASSWORD_LENGTH', '32')),
                'password_complexity': PasswordComplexity(
                    os.environ.get('PASSWORD_COMPLEXITY', 'high')
                ),
                'rotation_interval_days': int(os.environ.get('ROTATION_INTERVAL_DAYS', '30')),
            },
            'security': {
                'enable_ssl': os.environ.get('ENABLE_SSL', 'true').lower() == 'true',
                'ssl_mode': os.environ.get('SSL_MODE', 'require'),
                'enable_encryption': os.environ.get('ENABLE_ENCRYPTION', 'true').lower() == 'true',
            },
            'monitoring': {
                'enable_detailed_monitoring': os.environ.get('ENABLE_DETAILED_MONITORING', 'true').lower() == 'true',
                'enable_xray_tracing': os.environ.get('ENABLE_XRAY_TRACING', 'false').lower() == 'true',
                'cloudwatch_namespace': os.environ.get('CLOUDWATCH_NAMESPACE', 'AWS/SecretsManager/Rotation'),
            },
            'database': {
                'supported_engines': [engine.value for engine in DatabaseEngine],
                'connection_pool_size': int(os.environ.get('CONNECTION_POOL_SIZE', '5')),
                'query_timeout': int(os.environ.get('QUERY_TIMEOUT', '30')),
            }
        }
        
        # Environment-specific overrides
        if self.environment == Environment.DEV:
            self._apply_dev_config()
        elif self.environment == Environment.STAGING:
            self._apply_staging_config()
        elif self.environment == Environment.PROD:
            self._apply_prod_config()
    
    def _apply_dev_config(self) -> None:
        """Apply development environment configuration."""
        self.config.update({
            'lambda': {
                **self.config['lambda'],
                'log_level': 'DEBUG',
                'memory_size': 256,
            },
            'rotation': {
                **self.config['rotation'],
                'rotation_interval_days': 1,  # Daily rotation for testing
                'max_retries': 2,
            },
            'monitoring': {
                **self.config['monitoring'],
                'enable_detailed_monitoring': False,
                'enable_xray_tracing': True,  # Enable for debugging
            }
        })
    
    def _apply_staging_config(self) -> None:
        """Apply staging environment configuration."""
        self.config.update({
            'lambda': {
                **self.config['lambda'],
                'log_level': 'INFO',
                'memory_size': 512,
            },
            'rotation': {
                **self.config['rotation'],
                'rotation_interval_days': 7,  # Weekly rotation
                'max_retries': 3,
            },
            'monitoring': {
                **self.config['monitoring'],
                'enable_detailed_monitoring': True,
                'enable_xray_tracing': True,
            }
        })
    
    def _apply_prod_config(self) -> None:
        """Apply production environment configuration."""
        self.config.update({
            'lambda': {
                **self.config['lambda'],
                'log_level': 'INFO',
                'memory_size': 512,
                'timeout': 300,
            },
            'rotation': {
                **self.config['rotation'],
                'rotation_interval_days': 30,  # Monthly rotation
                'max_retries': 5,
                'password_complexity': PasswordComplexity.HIGH,
            },
            'security': {
                **self.config['security'],
                'enable_ssl': True,
                'ssl_mode': 'require',
                'enable_encryption': True,
            },
            'monitoring': {
                **self.config['monitoring'],
                'enable_detailed_monitoring': True,
                'enable_xray_tracing': False,  # Disable for performance
            }
        })
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key_path: Dot-separated path to configuration value
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_lambda_config(self) -> Dict[str, Any]:
        """Get Lambda-specific configuration."""
        return self.config['lambda']
    
    def get_rotation_config(self) -> Dict[str, Any]:
        """Get rotation-specific configuration."""
        return self.config['rotation']
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security-specific configuration."""
        return self.config['security']
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring-specific configuration."""
        return self.config['monitoring']
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database-specific configuration."""
        return self.config['database']
    
    def validate_secret_format(self, secret_dict: Dict[str, Any]) -> bool:
        """
        Validate secret dictionary format.
        
        Args:
            secret_dict: Secret dictionary to validate
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['engine', 'host', 'port', 'username', 'password']
        
        # Check required fields
        for field in required_fields:
            if field not in secret_dict:
                return False
        
        # Validate engine
        engine = secret_dict['engine'].lower()
        if engine not in [e.value for e in DatabaseEngine]:
            return False
        
        # Validate port
        try:
            port = int(secret_dict['port'])
            if not (1 <= port <= 65535):
                return False
        except (ValueError, TypeError):
            return False
        
        return True
    
    def get_password_policy(self) -> Dict[str, Any]:
        """
        Get password policy based on complexity level.
        
        Returns:
            Password policy configuration
        """
        complexity = self.config['rotation']['password_complexity']
        length = self.config['rotation']['password_length']
        
        if complexity == PasswordComplexity.HIGH:
            return {
                'length': length,
                'min_uppercase': 2,
                'min_lowercase': 2,
                'min_digits': 2,
                'min_special': 2,
                'allowed_special': "!@#$%^&*()_+-=[]{}|;:,.<>?",
                'exclude_ambiguous': True,
            }
        elif complexity == PasswordComplexity.MEDIUM:
            return {
                'length': length,
                'min_uppercase': 1,
                'min_lowercase': 1,
                'min_digits': 1,
                'min_special': 1,
                'allowed_special': "!@#$%^&*",
                'exclude_ambiguous': True,
            }
        else:  # LOW
            return {
                'length': length,
                'min_uppercase': 1,
                'min_lowercase': 1,
                'min_digits': 1,
                'min_special': 0,
                'allowed_special': "",
                'exclude_ambiguous': True,
            }
    
    def get_connection_config(self, engine: str) -> Dict[str, Any]:
        """
        Get database connection configuration for specific engine.
        
        Args:
            engine: Database engine name
            
        Returns:
            Connection configuration
        """
        base_config = {
            'timeout': self.config['rotation']['connection_timeout'],
            'pool_size': self.config['database']['connection_pool_size'],
            'query_timeout': self.config['database']['query_timeout'],
        }
        
        engine = engine.lower()
        
        if engine in ['postgres', 'postgresql']:
            return {
                **base_config,
                'sslmode': self.config['security']['ssl_mode'] if self.config['security']['enable_ssl'] else 'disable',
                'application_name': 'aws-secrets-rotation',
            }
        elif engine in ['mysql', 'mariadb']:
            return {
                **base_config,
                'ssl_disabled': not self.config['security']['enable_ssl'],
                'autocommit': True,
                'charset': 'utf8mb4',
            }
        elif engine == 'oracle':
            return {
                **base_config,
                'encoding': 'UTF-8',
                'threaded': True,
            }
        
        return base_config
    
    def __str__(self) -> str:
        """String representation of configuration."""
        return f"Config(environment={self.environment.value})"
    
    def __repr__(self) -> str:
        """Detailed string representation of configuration."""
        return f"Config(environment={self.environment.value}, config={self.config})"

# Global configuration instance
config = Config()

# Convenience functions
def get_config(key_path: str, default: Any = None) -> Any:
    """Get configuration value using global config instance."""
    return config.get(key_path, default)

def get_lambda_config() -> Dict[str, Any]:
    """Get Lambda configuration using global config instance."""
    return config.get_lambda_config()

def get_rotation_config() -> Dict[str, Any]:
    """Get rotation configuration using global config instance."""
    return config.get_rotation_config()

def get_security_config() -> Dict[str, Any]:
    """Get security configuration using global config instance."""
    return config.get_security_config()

def get_monitoring_config() -> Dict[str, Any]:
    """Get monitoring configuration using global config instance."""
    return config.get_monitoring_config()

def get_database_config() -> Dict[str, Any]:
    """Get database configuration using global config instance."""
    return config.get_database_config()
