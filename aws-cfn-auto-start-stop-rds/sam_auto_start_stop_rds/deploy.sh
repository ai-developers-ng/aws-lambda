#!/bin/bash

# Improved RDS Auto Start/Stop Deployment Script
# Version: 2.0.0
# Author: Improved by AI Assistant

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
STACK_NAME="rds-auto-start-stop-improved"
REGION=""
S3_BUCKET=""
NOTIFICATION_EMAIL=""
TIMEZONE="UTC"
LOG_LEVEL="INFO"
ENABLE_MONITORING="true"
TEMPLATE_FILE="sam_auto_start_stop_rds_improved.yaml"

# Function to print colored output
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to print usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy the improved RDS Auto Start/Stop solution using AWS SAM.

OPTIONS:
    -s, --stack-name STACK_NAME         CloudFormation stack name (default: rds-auto-start-stop-improved)
    -r, --region REGION                 AWS region (required)
    -b, --s3-bucket BUCKET              S3 bucket for deployment artifacts (required)
    -e, --email EMAIL                   Email for error notifications (optional)
    -t, --timezone TIMEZONE             Timezone for flexible schedules (default: UTC)
    -l, --log-level LEVEL               Log level: DEBUG|INFO|WARNING|ERROR (default: INFO)
    -m, --monitoring BOOL               Enable detailed monitoring: true|false (default: true)
    --template TEMPLATE                 SAM template file (default: sam_auto_start_stop_rds_improved.yaml)
    --guided                            Use SAM guided deployment
    --validate-only                     Only validate the template
    --delete                            Delete the stack
    -h, --help                          Show this help message

EXAMPLES:
    # Basic deployment
    $0 -r us-east-1 -b my-deployment-bucket

    # Full deployment with monitoring and notifications
    $0 -r us-east-1 -b my-deployment-bucket -e admin@example.com -t US/Eastern

    # Guided deployment
    $0 --guided

    # Validate template only
    $0 --validate-only

    # Delete stack
    $0 --delete -s my-stack-name -r us-east-1

EOF
}

# Function to validate prerequisites
validate_prerequisites() {
    print_message $BLUE "Validating prerequisites..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        print_message $RED "Error: AWS CLI is not installed"
        exit 1
    fi
    
    # Check if SAM CLI is installed
    if ! command -v sam &> /dev/null; then
        print_message $RED "Error: SAM CLI is not installed"
        exit 1
    fi
    
    # Check if Python is installed
    if ! command -v python3 &> /dev/null; then
        print_message $RED "Error: Python 3 is not installed"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_message $RED "Error: AWS credentials not configured"
        exit 1
    fi
    
    print_message $GREEN "Prerequisites validated successfully"
}

# Function to validate template
validate_template() {
    print_message $BLUE "Validating SAM template..."
    
    if ! sam validate --template-file "$TEMPLATE_FILE"; then
        print_message $RED "Error: Template validation failed"
        exit 1
    fi
    
    print_message $GREEN "Template validation successful"
}

# Function to check if S3 bucket exists
check_s3_bucket() {
    if [ -n "$S3_BUCKET" ]; then
        print_message $BLUE "Checking S3 bucket: $S3_BUCKET"
        
        if ! aws s3 ls "s3://$S3_BUCKET" &> /dev/null; then
            print_message $YELLOW "S3 bucket $S3_BUCKET does not exist or is not accessible"
            read -p "Do you want to create it? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                aws s3 mb "s3://$S3_BUCKET" --region "$REGION"
                print_message $GREEN "S3 bucket created successfully"
            else
                print_message $RED "Deployment cannot continue without S3 bucket"
                exit 1
            fi
        else
            print_message $GREEN "S3 bucket exists and is accessible"
        fi
    fi
}

# Function to build SAM application
build_sam_app() {
    print_message $BLUE "Building SAM application..."
    
    if ! sam build --template-file "$TEMPLATE_FILE"; then
        print_message $RED "Error: SAM build failed"
        exit 1
    fi
    
    print_message $GREEN "SAM build completed successfully"
}

# Function to deploy with guided mode
deploy_guided() {
    print_message $BLUE "Starting guided deployment..."
    
    sam deploy --guided --template-file "$TEMPLATE_FILE"
}

# Function to deploy with parameters
deploy_with_params() {
    print_message $BLUE "Deploying with specified parameters..."
    
    local params=""
    
    if [ -n "$NOTIFICATION_EMAIL" ]; then
        params="$params NotificationEmail=$NOTIFICATION_EMAIL"
    fi
    
    params="$params RegionTZ=$TIMEZONE"
    params="$params LogLevel=$LOG_LEVEL"
    params="$params EnableDetailedMonitoring=$ENABLE_MONITORING"
    
    sam deploy \
        --template-file "$TEMPLATE_FILE" \
        --stack-name "$STACK_NAME" \
        --s3-bucket "$S3_BUCKET" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --parameter-overrides $params \
        --tags Project=RDS-Auto-Start-Stop Version=2.0.0 \
        --no-fail-on-empty-changeset
}

# Function to delete stack
delete_stack() {
    print_message $YELLOW "Deleting stack: $STACK_NAME"
    
    read -p "Are you sure you want to delete the stack? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
        print_message $GREEN "Stack deletion initiated"
        
        print_message $BLUE "Waiting for stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$REGION"
        print_message $GREEN "Stack deleted successfully"
    else
        print_message $YELLOW "Stack deletion cancelled"
    fi
}

# Function to run tests
run_tests() {
    print_message $BLUE "Running unit tests..."
    
    if [ -d "tests" ]; then
        cd tests
        if command -v pytest &> /dev/null; then
            python -m pytest -v
        else
            python -m unittest discover -v
        fi
        cd ..
        print_message $GREEN "Tests completed"
    else
        print_message $YELLOW "No tests directory found, skipping tests"
    fi
}

# Function to display deployment info
display_deployment_info() {
    print_message $GREEN "Deployment completed successfully!"
    print_message $BLUE "Stack Information:"
    
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
        --output table
    
    print_message $BLUE "Next Steps:"
    echo "1. Tag your RDS instances with appropriate tags (AutoStart, AutoStop, etc.)"
    echo "2. Monitor the CloudWatch dashboard for execution status"
    echo "3. Check CloudWatch logs for detailed execution information"
    
    if [ -n "$NOTIFICATION_EMAIL" ]; then
        echo "4. Check your email for SNS subscription confirmation"
    fi
}

# Parse command line arguments
GUIDED_MODE=false
VALIDATE_ONLY=false
DELETE_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -b|--s3-bucket)
            S3_BUCKET="$2"
            shift 2
            ;;
        -e|--email)
            NOTIFICATION_EMAIL="$2"
            shift 2
            ;;
        -t|--timezone)
            TIMEZONE="$2"
            shift 2
            ;;
        -l|--log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        -m|--monitoring)
            ENABLE_MONITORING="$2"
            shift 2
            ;;
        --template)
            TEMPLATE_FILE="$2"
            shift 2
            ;;
        --guided)
            GUIDED_MODE=true
            shift
            ;;
        --validate-only)
            VALIDATE_ONLY=true
            shift
            ;;
        --delete)
            DELETE_MODE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_message $RED "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_message $GREEN "=== RDS Auto Start/Stop Improved Deployment ==="
    
    validate_prerequisites
    
    if [ "$VALIDATE_ONLY" = true ]; then
        validate_template
        print_message $GREEN "Template validation completed"
        exit 0
    fi
    
    if [ "$DELETE_MODE" = true ]; then
        if [ -z "$REGION" ]; then
            print_message $RED "Error: Region is required for stack deletion"
            exit 1
        fi
        delete_stack
        exit 0
    fi
    
    validate_template
    
    if [ "$GUIDED_MODE" = true ]; then
        build_sam_app
        deploy_guided
    else
        # Validate required parameters
        if [ -z "$REGION" ] || [ -z "$S3_BUCKET" ]; then
            print_message $RED "Error: Region and S3 bucket are required for non-guided deployment"
            usage
            exit 1
        fi
        
        check_s3_bucket
        build_sam_app
        deploy_with_params
        display_deployment_info
    fi
    
    print_message $GREEN "Deployment process completed!"
}

# Run main function
main "$@"
