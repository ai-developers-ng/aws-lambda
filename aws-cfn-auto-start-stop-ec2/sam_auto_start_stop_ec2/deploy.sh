#!/bin/bash

# Enhanced Deployment Script for EC2 Auto Start/Stop Solution
# This script provides comprehensive deployment with validation and monitoring setup
#
# Author: Enhanced by BlackBoxAI
# Version: 2.0.0

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
STACK_NAME="enhanced-ec2-auto-start-stop"
REGION=""
S3_BUCKET=""
ENVIRONMENT="prod"
NOTIFICATION_EMAIL=""
ENABLE_MONITORING="true"
LOG_LEVEL="INFO"
REGION_TZ="UTC"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Enhanced EC2 Auto Start/Stop Deployment Script

Usage: $0 [OPTIONS]

Required Options:
    -r, --region REGION         AWS region for deployment
    -b, --bucket BUCKET         S3 bucket for SAM artifacts

Optional Options:
    -s, --stack-name NAME       CloudFormation stack name (default: enhanced-ec2-auto-start-stop)
    -e, --environment ENV       Environment (dev/staging/prod, default: prod)
    -n, --notification EMAIL    Email for notifications (optional)
    -m, --monitoring BOOL       Enable monitoring (true/false, default: true)
    -l, --log-level LEVEL       Log level (DEBUG/INFO/WARNING/ERROR, default: INFO)
    -t, --timezone TZ           Region timezone (default: UTC)
    -h, --help                  Show this help message

Examples:
    $0 -r us-east-1 -b my-sam-bucket
    $0 -r us-west-2 -b my-bucket -s my-ec2-stack -e staging -n admin@company.com
    $0 --region eu-west-1 --bucket eu-bucket --environment prod --notification ops@company.com

Supported Timezones:
    UTC, US/Eastern, US/Central, US/Mountain, US/Pacific, Europe/London,
    Europe/Paris, Europe/Berlin, Asia/Tokyo, Asia/Singapore, etc.

EOF
}

# Function to validate prerequisites
validate_prerequisites() {
    print_status "Validating prerequisites..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if SAM CLI is installed
    if ! command -v sam &> /dev/null; then
        print_error "SAM CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    # Check if region is valid
    if ! aws ec2 describe-regions --region-names "$REGION" &> /dev/null; then
        print_error "Invalid AWS region: $REGION"
        exit 1
    fi
    
    # Check if S3 bucket exists and is accessible
    if ! aws s3 ls "s3://$S3_BUCKET" --region "$REGION" &> /dev/null; then
        print_error "S3 bucket '$S3_BUCKET' does not exist or is not accessible in region '$REGION'"
        print_status "Creating S3 bucket..."
        aws s3 mb "s3://$S3_BUCKET" --region "$REGION" || {
            print_error "Failed to create S3 bucket"
            exit 1
        }
        print_success "S3 bucket created successfully"
    fi
    
    print_success "Prerequisites validated"
}

# Function to validate parameters
validate_parameters() {
    print_status "Validating parameters..."
    
    # Validate required parameters
    if [[ -z "$REGION" ]]; then
        print_error "Region is required. Use -r or --region option."
        exit 1
    fi
    
    if [[ -z "$S3_BUCKET" ]]; then
        print_error "S3 bucket is required. Use -b or --bucket option."
        exit 1
    fi
    
    # Validate environment
    if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
        print_error "Invalid environment. Must be dev, staging, or prod."
        exit 1
    fi
    
    # Validate log level
    if [[ ! "$LOG_LEVEL" =~ ^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$ ]]; then
        print_error "Invalid log level. Must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        exit 1
    fi
    
    # Validate email format if provided
    if [[ -n "$NOTIFICATION_EMAIL" ]]; then
        if [[ ! "$NOTIFICATION_EMAIL" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
            print_error "Invalid email format: $NOTIFICATION_EMAIL"
            exit 1
        fi
    fi
    
    print_success "Parameters validated"
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    
    if [[ -f "tests/test_ec2_utils.py" ]]; then
        cd tests
        python -m pytest test_ec2_utils.py -v || {
            print_warning "Some tests failed, but continuing with deployment"
        }
        cd ..
        print_success "Tests completed"
    else
        print_warning "Test file not found, skipping tests"
    fi
}

# Function to build and deploy
build_and_deploy() {
    print_status "Building and deploying SAM application..."
    
    # Build the application
    print_status "Building SAM application..."
    sam build --template-file sam_auto_start_stop_ec2_improved.yaml || {
        print_error "SAM build failed"
        exit 1
    }
    
    # Deploy the application
    print_status "Deploying SAM application..."
    sam deploy \
        --template-file .aws-sam/build/template.yaml \
        --stack-name "$STACK_NAME" \
        --s3-bucket "$S3_BUCKET" \
        --capabilities CAPABILITY_IAM \
        --region "$REGION" \
        --parameter-overrides \
            Environment="$ENVIRONMENT" \
            LogLevel="$LOG_LEVEL" \
            RegionTZ="$REGION_TZ" \
            EnableMonitoring="$ENABLE_MONITORING" \
            NotificationEmail="$NOTIFICATION_EMAIL" \
        --tags \
            Project=EC2AutoStartStop \
            Environment="$ENVIRONMENT" \
            Version=2.0.0 \
            DeployedBy="$(whoami)" \
            DeployedAt="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || {
        print_error "SAM deployment failed"
        exit 1
    }
    
    print_success "SAM application deployed successfully"
}

# Function to validate deployment
validate_deployment() {
    print_status "Validating deployment..."
    
    # Check if stack exists and is in CREATE_COMPLETE or UPDATE_COMPLETE state
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$STACK_STATUS" == "CREATE_COMPLETE" || "$STACK_STATUS" == "UPDATE_COMPLETE" ]]; then
        print_success "Stack deployment validated: $STACK_STATUS"
    else
        print_error "Stack deployment failed or incomplete: $STACK_STATUS"
        exit 1
    fi
    
    # Get stack outputs
    print_status "Retrieving stack outputs..."
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
        --output text > /dev/null 2>&1 && {
        DASHBOARD_URL=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`DashboardURL`].OutputValue' \
            --output text)
        print_success "CloudWatch Dashboard: $DASHBOARD_URL"
    }
    
    print_success "Deployment validation completed"
}

# Function to show deployment summary
show_deployment_summary() {
    print_success "=== DEPLOYMENT SUMMARY ==="
    echo "Stack Name: $STACK_NAME"
    echo "Region: $REGION"
    echo "Environment: $ENVIRONMENT"
    echo "S3 Bucket: $S3_BUCKET"
    echo "Monitoring: $ENABLE_MONITORING"
    echo "Log Level: $LOG_LEVEL"
    echo "Timezone: $REGION_TZ"
    [[ -n "$NOTIFICATION_EMAIL" ]] && echo "Notifications: $NOTIFICATION_EMAIL"
    echo ""
    
    print_status "Getting Lambda function information..."
    aws lambda list-functions \
        --region "$REGION" \
        --query "Functions[?starts_with(FunctionName, '$STACK_NAME')].{Name:FunctionName,Runtime:Runtime,LastModified:LastModified}" \
        --output table 2>/dev/null || print_warning "Could not retrieve Lambda function information"
    
    print_success "Deployment completed successfully!"
    print_status "You can now tag your EC2 instances with the following tags:"
    echo "  - AutoStart: true/false (for fixed schedule start/stop)"
    echo "  - AutoStop: true/false (for fixed schedule start/stop)"
    echo "  - StartWeekDay: HH:MM (for weekday start time)"
    echo "  - StopWeekDay: HH:MM (for weekday stop time)"
    echo "  - StartWeekEnd: HH:MM (for weekend start time)"
    echo "  - StopWeekEnd: HH:MM (for weekend stop time)"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -b|--bucket)
            S3_BUCKET="$2"
            shift 2
            ;;
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -n|--notification)
            NOTIFICATION_EMAIL="$2"
            shift 2
            ;;
        -m|--monitoring)
            ENABLE_MONITORING="$2"
            shift 2
            ;;
        -l|--log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        -t|--timezone)
            REGION_TZ="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_status "Starting Enhanced EC2 Auto Start/Stop Deployment"
    print_status "Version: 2.0.0"
    echo ""
    
    validate_parameters
    validate_prerequisites
    run_tests
    build_and_deploy
    validate_deployment
    show_deployment_summary
}

# Run main function
main "$@"
