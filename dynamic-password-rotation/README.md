# Unified Database Password Rotation

A production-ready AWS Lambda function for automatic database password rotation using AWS Secrets Manager. Supports PostgreSQL, MySQL/MariaDB, and Oracle databases with comprehensive security, monitoring, and error handling.

## 🚀 Features

- **Multi-Database Support**: PostgreSQL, MySQL/MariaDB, and Oracle
- **Production-Ready**: Comprehensive error handling, retry logic, and monitoring
- **Security-First**: Secure password generation, encrypted storage, and parameterized queries
- **Environment-Aware**: Configurable settings for dev, staging, and production
- **Comprehensive Monitoring**: CloudWatch metrics, alarms, and dashboards
- **VPC Support**: Deploy within VPC for secure database access
- **Dead Letter Queue**: Failed rotation handling and alerting
- **Automated Testing**: Complete test suite with mocking and integration tests

## 📋 Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.11 or later
- Docker (for local testing)
- jq (for deployment script)

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Secrets       │    │    Lambda        │    │   Database      │
│   Manager       │───▶│   Function       │───▶│   (PG/MySQL/    │
│                 │    │                  │    │    Oracle)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌──────────────────┐            │
         │              │   CloudWatch     │            │
         └──────────────│   Monitoring     │────────────┘
                        └──────────────────┘
```

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd aws-lambda/dynamic-password-rotation
```

### 2. Configure Your Secret

Create a secret in AWS Secrets Manager with the following format:

```json
{
  "engine": "postgresql",
  "host": "your-db-host.amazonaws.com",
  "port": "5432",
  "username": "your-username",
  "password": "your-current-password",
  "dbname": "your-database-name"
}
```

### 3. Deploy

```bash
# Basic deployment
./deploy.sh -e dev -r us-west-2 -s arn:aws:secretsmanager:us-west-2:123456789012:secret:mydb-abc123

# Production deployment with VPC and notifications
./deploy.sh -e prod -r us-west-2 \
  -s arn:aws:secretsmanager:us-west-2:123456789012:secret:mydb-abc123 \
  -v vpc-12345678 \
  -n subnet-12345678,subnet-87654321 \
  -m admin@company.com
```

## 📖 Detailed Documentation

### Supported Database Engines

#### PostgreSQL
- **Engines**: `postgresql`, `postgres`
- **Required Fields**: `engine`, `host`, `port`, `username`, `password`, `dbname`
- **SSL**: Enabled by default with `sslmode=require`

#### MySQL/MariaDB
- **Engines**: `mysql`, `mariadb`
- **Required Fields**: `engine`, `host`, `port`, `username`, `password`, `dbname`
- **SSL**: Configurable, enabled by default

#### Oracle
- **Engines**: `oracle`
- **Required Fields**: `engine`, `host`, `port`, `username`, `password`
- **Optional Fields**: `sid` (defaults to `ORCL`)

### Environment Configuration

The solution supports three environments with different default settings:

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| Rotation Interval | 1 day | 7 days | 30 days |
| Log Level | DEBUG | INFO | INFO |
| Memory Size | 256 MB | 512 MB | 512 MB |
| Detailed Monitoring | Disabled | Enabled | Enabled |
| Max Retries | 2 | 3 | 5 |

### Password Generation

Passwords are generated using cryptographically secure methods with configurable complexity:

- **High Complexity** (default): 32 characters, uppercase, lowercase, digits, special characters
- **Medium Complexity**: 24 characters, basic character set
- **Low Complexity**: 16 characters, alphanumeric only

### Deployment Options

#### Command Line Parameters

```bash
./deploy.sh [OPTIONS]

OPTIONS:
    -e, --environment ENV       Environment (dev, staging, prod) [default: dev]
    -r, --region REGION         AWS region [required]
    -p, --profile PROFILE       AWS profile to use
    -s, --secret-arn ARN        Secrets Manager secret ARN [required]
    -v, --vpc-id VPC_ID         VPC ID for Lambda deployment
    -n, --subnet-ids SUBNETS    Comma-separated subnet IDs
    -k, --kms-key-id KEY_ID     KMS key ID for encryption
    -m, --notification-email EMAIL  Email for failure notifications
    -d, --dry-run               Show what would be deployed without executing
    -t, --validate-only         Only validate the template
    -f, --force                 Force deployment without confirmation
    -h, --help                  Show help message
```

#### CloudFormation Parameters

The CloudFormation template supports extensive customization:

- **VPC Configuration**: Deploy Lambda in VPC for secure database access
- **KMS Encryption**: Custom KMS keys for enhanced security
- **Monitoring**: Configurable CloudWatch alarms and dashboards
- **Notifications**: SNS integration for failure alerts
- **Resource Tagging**: Comprehensive tagging for resource management

### Security Features

#### Password Security
- Cryptographically secure password generation using `secrets` module
- Configurable password complexity and length
- No password logging or exposure in CloudWatch logs

#### Database Security
- Parameterized queries to prevent SQL injection
- SSL/TLS encryption for database connections
- Connection timeouts and proper resource cleanup

#### AWS Security
- Least privilege IAM permissions
- KMS encryption for secrets and logs
- VPC deployment support for network isolation
- Dead letter queues for failed operations

### Monitoring and Alerting

#### CloudWatch Metrics
- Custom metrics for rotation success/failure by step
- Lambda function metrics (duration, errors, invocations)
- Database connection metrics

#### CloudWatch Alarms
- Rotation error detection
- Long-running rotation detection
- Failed connection alerts

#### CloudWatch Dashboard
- Real-time rotation status
- Historical success/failure rates
- Performance metrics visualization

### Error Handling

#### Retry Logic
- Configurable retry attempts with exponential backoff
- Step-specific error handling
- Graceful degradation for transient failures

#### Dead Letter Queue
- Failed rotations sent to DLQ for investigation
- Configurable message retention
- Integration with monitoring and alerting

#### Custom Exceptions
- `RotationError`: Base exception for rotation issues
- `DatabaseConnectionError`: Database-specific errors
- `PasswordGenerationError`: Password generation failures

## 🧪 Testing

### Running Tests

```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=lambda_function --cov-report=html

# Run specific test class
python -m pytest tests/test_rotation.py::TestPasswordGeneration -v
```

### Test Categories

- **Unit Tests**: Individual function testing with mocking
- **Integration Tests**: End-to-end rotation workflow testing
- **Security Tests**: Password generation and SQL injection prevention
- **Error Handling Tests**: Exception scenarios and recovery

### Local Development

```bash
# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r tests/requirements-test.txt

# Run linting
flake8 lambda_function.py
black lambda_function.py --check
mypy lambda_function.py

# Security scanning
bandit -r lambda_function.py
```

## 🔧 Configuration

### Environment Variables

The Lambda function supports the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MAX_RETRIES` | `3` | Maximum retry attempts |
| `RETRY_DELAY` | `5` | Delay between retries (seconds) |
| `CONNECTION_TIMEOUT` | `30` | Database connection timeout (seconds) |
| `PASSWORD_LENGTH` | `32` | Generated password length |
| `PASSWORD_COMPLEXITY` | `high` | Password complexity (low, medium, high) |
| `ENVIRONMENT` | `dev` | Deployment environment |

### Secret Format

Secrets must follow this JSON format:

```json
{
  "engine": "postgresql|mysql|mariadb|oracle",
  "host": "database-hostname",
  "port": "database-port",
  "username": "database-username",
  "password": "current-password",
  "dbname": "database-name",
  "sid": "oracle-sid (Oracle only, optional)"
}
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Permission Denied
**Error**: `AccessDenied` when accessing secrets
**Solution**: Verify IAM permissions for Secrets Manager and KMS

#### 2. Database Connection Timeout
**Error**: Connection timeout to database
**Solution**: Check VPC configuration, security groups, and network ACLs

#### 3. Password Complexity Issues
**Error**: Generated password doesn't meet database requirements
**Solution**: Adjust `PASSWORD_COMPLEXITY` and `PASSWORD_LENGTH` environment variables

#### 4. Rotation Schedule Not Working
**Error**: Automatic rotation not triggering
**Solution**: Verify rotation schedule is enabled and Lambda permissions are correct

### Debugging

#### Enable Debug Logging
```bash
# Update environment variable
aws lambda update-function-configuration \
  --function-name unified-db-rotation-dev \
  --environment Variables='{LOG_LEVEL=DEBUG}'
```

#### Check CloudWatch Logs
```bash
# View recent logs
aws logs tail /aws/lambda/unified-db-rotation-dev --follow
```

#### Monitor Metrics
```bash
# Get rotation metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/SecretsManager/Rotation \
  --metric-name RotationSuccess \
  --start-time 2023-01-01T00:00:00Z \
  --end-time 2023-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

## 🔄 Maintenance

### Regular Tasks

1. **Monitor Rotation Success**: Check CloudWatch dashboards weekly
2. **Review Logs**: Investigate any ERROR or WARNING messages
3. **Update Dependencies**: Keep database drivers and boto3 updated
4. **Test Connectivity**: Verify database connectivity monthly
5. **Review Permissions**: Audit IAM permissions quarterly

### Updates and Upgrades

#### Updating Lambda Code
```bash
# Redeploy with latest code
./deploy.sh -e prod -r us-west-2 -s <secret-arn> -f
```

#### Updating Dependencies
```bash
# Update requirements.txt and redeploy
pip freeze > requirements.txt
./deploy.sh -e prod -r us-west-2 -s <secret-arn> -f
```

## 📊 Performance Considerations

### Lambda Configuration
- **Memory**: 512 MB recommended for production
- **Timeout**: 300 seconds (5 minutes) maximum
- **Concurrency**: Limited to prevent database connection exhaustion

### Database Considerations
- **Connection Limits**: Monitor database connection usage
- **Performance Impact**: Rotation typically takes 10-30 seconds
- **Maintenance Windows**: Schedule rotations during low-traffic periods

## 🔐 Security Best Practices

1. **Use VPC**: Deploy Lambda in VPC for network isolation
2. **Enable KMS**: Use customer-managed KMS keys for encryption
3. **Least Privilege**: Grant minimal required IAM permissions
4. **Monitor Access**: Enable CloudTrail for API call auditing
5. **Regular Rotation**: Use appropriate rotation intervals for your security requirements
6. **Test Regularly**: Validate rotation functionality monthly

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## 📞 Support

For issues and questions:

1. Check the troubleshooting section
2. Review CloudWatch logs and metrics
3. Create an issue in the repository
4. Contact your AWS support team for AWS-specific issues

## 🔄 Changelog

### Version 2.0.0 (Current)
- Complete rewrite for production readiness
- Added comprehensive error handling and retry logic
- Implemented secure password generation
- Added multi-environment support
- Enhanced monitoring and alerting
- Added comprehensive test suite
- Improved security with parameterized queries
- Added VPC and KMS support

### Version 1.0.0 (Legacy)
- Basic password rotation functionality
- Limited error handling
- Single environment support
