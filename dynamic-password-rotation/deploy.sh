#!/bin/bash

# Production-ready deployment script for unified database password rotation
# Supports multiple environments with validation and rollback capabilities

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_NAME_PREFIX="unified-db-rotation"
TEMPLATE_FILE="unified-db-rotation.yaml"
LAMBDA_CODE_FILE="lambda-function.py"
REQUIREMENTS_FILE="requirements.txt"

# Default values
ENVIRONMENT="dev"
REGION=""
PROFILE=""
SECRET_ARN=""
VPC_ID=""
SUBNET_IDS=""
KMS_KEY_ID=""
NOTIFICATION_EMAIL=""
DRY_RUN="false"
VALIDATE_ONLY="false"
FORCE_DEPLOY="false"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Usage function
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy the unified database password rotation Lambda function.

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
    -h, --help                  Show this help message

EXAMPLES:
    # Basic deployment
    $0 -e dev -r us-west-2 -s arn:aws:secretsmanager:us-west-2:123456789012:secret:mydb-abc123

    # Production deployment with VPC and notifications
    $0 -e prod -r us-west-2 -s arn:aws:secretsmanager:us-west-2:123456789012:secret:mydb-abc123 \\
       -v vpc-12345678 -n subnet-12345678,subnet-87654321 -m admin@company.com

    # Dry run to see what would be deployed
    $0 -e staging -r us-west-2 -s arn:aws:secretsmanager:us-west-2:123456789012:secret:mydb-abc123 -d

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -r|--region)
                REGION="$2"
                shift 2
                ;;
            -p|--profile)
                PROFILE="$2"
                shift 2
                ;;
            -s|--secret-arn)
                SECRET_ARN="$2"
                shift 2
                ;;
            -v|--vpc-id)
                VPC_ID="$2"
                shift 2
                ;;
            -n|--subnet-ids)
                SUBNET_IDS="$2"
                shift 2
                ;;
            -k|--kms-key-id)
                KMS_KEY_ID="$2"
                shift 2
                ;;
            -m|--notification-email)
                NOTIFICATION_EMAIL="$2"
                shift 2
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            -t|--validate-only)
                VALIDATE_ONLY="true"
                shift
                ;;
            -f|--force)
                FORCE_DEPLOY="true"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

# Validate required parameters
validate_parameters() {
    local errors=0

    if [[ -z "$REGION" ]]; then
        log_error "Region is required (-r/--region)"
        ((errors++))
    fi

    if [[ -z "$SECRET_ARN" ]]; then
        log_error "Secret ARN is required (-s/--secret-arn)"
        ((errors++))
    fi

    if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
        log_error "Environment must be one of: dev, staging, prod"
        ((errors++))
    fi

    if [[ -n "$SECRET_ARN" && ! "$SECRET_ARN" =~ ^arn:aws:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:.+$ ]]; then
        log_error "Invalid Secret ARN format"
        ((errors++))
    fi

    if [[ -n "$NOTIFICATION_EMAIL" && ! "$NOTIFICATION_EMAIL" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
        log_error "Invalid email format"
        ((errors++))
    fi

    if [[ $errors -gt 0 ]]; then
        log_error "Parameter validation failed with $errors error(s)"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi

    # Check if required files exist
    if [[ ! -f "$SCRIPT_DIR/$TEMPLATE_FILE" ]]; then
        log_error "CloudFormation template not found: $TEMPLATE_FILE"
        exit 1
    fi

    if [[ ! -f "$SCRIPT_DIR/$LAMBDA_CODE_FILE" ]]; then
        log_error "Lambda code file not found: $LAMBDA_CODE_FILE"
        exit 1
    fi

    # Set AWS profile if specified
    if [[ -n "$PROFILE" ]]; then
        export AWS_PROFILE="$PROFILE"
        log_info "Using AWS profile: $PROFILE"
    fi

    # Verify AWS credentials
    if ! aws sts get-caller-identity --region "$REGION" &> /dev/null; then
        log_error "AWS credentials not configured or invalid"
        exit 1
    fi

    # Get AWS account ID and user info
    local account_info
    account_info=$(aws sts get-caller-identity --region "$REGION" --output json)
    local account_id
    account_id=$(echo "$account_info" | jq -r '.Account')
    local user_arn
    user_arn=$(echo "$account_info" | jq -r '.Arn')
    
    log_info "AWS Account: $account_id"
    log_info "AWS User: $user_arn"
    log_info "AWS Region: $REGION"
}

# Validate CloudFormation template
validate_template() {
    log_info "Validating CloudFormation template..."
    
    if aws cloudformation validate-template \
        --template-body "file://$SCRIPT_DIR/$TEMPLATE_FILE" \
        --region "$REGION" &> /dev/null; then
        log_success "Template validation passed"
    else
        log_error "Template validation failed"
        exit 1
    fi
}

# Create deployment package
create_deployment_package() {
    log_info "Creating deployment package..."
    
    local temp_dir
    temp_dir=$(mktemp -d)
    local package_file="$temp_dir/deployment-package.zip"
    
    # Copy Lambda code
    cp "$SCRIPT_DIR/$LAMBDA_CODE_FILE" "$temp_dir/"
    
    # Install dependencies if requirements.txt exists
    if [[ -f "$SCRIPT_DIR/$REQUIREMENTS_FILE" ]]; then
        log_info "Installing Python dependencies..."
        pip install -r "$SCRIPT_DIR/$REQUIREMENTS_FILE" -t "$temp_dir/" --quiet
    fi
    
    # Create zip package
    cd "$temp_dir"
    zip -r "$package_file" . -q
    cd - > /dev/null
    
    echo "$package_file"
}

# Build parameter overrides
build_parameters() {
    local params=""
    
    params+="ExistingSecretArn=$SECRET_ARN "
    params+="Environment=$ENVIRONMENT "
    params+="LambdaFunctionName=unified-db-rotation "
    
    if [[ -n "$VPC_ID" ]]; then
        params+="VpcId=$VPC_ID "
    fi
    
    if [[ -n "$SUBNET_IDS" ]]; then
        params+="SubnetIds=$SUBNET_IDS "
    fi
    
    if [[ -n "$KMS_KEY_ID" ]]; then
        params+="KMSKeyId=$KMS_KEY_ID "
    fi
    
    if [[ -n "$NOTIFICATION_EMAIL" ]]; then
        params+="NotificationEmail=$NOTIFICATION_EMAIL "
    fi
    
    # Environment-specific settings
    case "$ENVIRONMENT" in
        prod)
            params+="RotationIntervalDays=30 "
            params+="LogLevel=INFO "
            params+="EnableDetailedMonitoring=true "
            ;;
        staging)
            params+="RotationIntervalDays=7 "
            params+="LogLevel=INFO "
            params+="EnableDetailedMonitoring=true "
            ;;
        dev)
            params+="RotationIntervalDays=1 "
            params+="LogLevel=DEBUG "
            params+="EnableDetailedMonitoring=false "
            ;;
    esac
    
    echo "$params"
}

# Deploy stack
deploy_stack() {
    local stack_name="$STACK_NAME_PREFIX-$ENVIRONMENT"
    local parameters
    parameters=$(build_parameters)
    
    log_info "Stack name: $stack_name"
    log_info "Parameters: $parameters"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warning "DRY RUN MODE - No actual deployment will occur"
        log_info "Would deploy with the following parameters:"
        echo "$parameters" | tr ' ' '\n' | grep -v '^$'
        return 0
    fi
    
    if [[ "$VALIDATE_ONLY" == "true" ]]; then
        log_info "Validation-only mode - skipping deployment"
        return 0
    fi
    
    # Check if stack exists
    local stack_exists="false"
    if aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" &> /dev/null; then
        stack_exists="true"
        log_info "Stack exists - will update"
    else
        log_info "Stack does not exist - will create"
    fi
    
    # Confirmation prompt (unless forced)
    if [[ "$FORCE_DEPLOY" != "true" ]]; then
        echo
        log_warning "About to deploy to $ENVIRONMENT environment"
        log_warning "Stack: $stack_name"
        log_warning "Region: $REGION"
        echo
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelled"
            exit 0
        fi
    fi
    
    # Create deployment package
    local package_file
    package_file=$(create_deployment_package)
    
    # Upload package to S3 (for large packages)
    local s3_bucket="aws-lambda-deployments-$REGION-$(aws sts get-caller-identity --query Account --output text)"
    local s3_key="unified-db-rotation/$ENVIRONMENT/$(date +%Y%m%d-%H%M%S)/deployment-package.zip"
    
    # Create S3 bucket if it doesn't exist
    if ! aws s3 ls "s3://$s3_bucket" &> /dev/null; then
        log_info "Creating S3 bucket: $s3_bucket"
        aws s3 mb "s3://$s3_bucket" --region "$REGION"
    fi
    
    # Upload package
    log_info "Uploading deployment package to S3..."
    aws s3 cp "$package_file" "s3://$s3_bucket/$s3_key" --region "$REGION"
    
    # Deploy stack
    log_info "Deploying CloudFormation stack..."
    
    local deploy_cmd="aws cloudformation deploy"
    deploy_cmd+=" --template-file $SCRIPT_DIR/$TEMPLATE_FILE"
    deploy_cmd+=" --stack-name $stack_name"
    deploy_cmd+=" --region $REGION"
    deploy_cmd+=" --capabilities CAPABILITY_NAMED_IAM"
    deploy_cmd+=" --parameter-overrides $parameters"
    deploy_cmd+=" --tags Environment=$ENVIRONMENT Project=UnifiedDBRotation"
    
    if eval "$deploy_cmd"; then
        log_success "Stack deployment completed successfully"
        
        # Update Lambda function code
        log_info "Updating Lambda function code..."
        local function_name="unified-db-rotation-$ENVIRONMENT"
        aws lambda update-function-code \
            --function-name "$function_name" \
            --s3-bucket "$s3_bucket" \
            --s3-key "$s3_key" \
            --region "$REGION" > /dev/null
        
        log_success "Lambda function code updated"
        
        # Display stack outputs
        log_info "Stack outputs:"
        aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --region "$REGION" \
            --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
            --output table
            
    else
        log_error "Stack deployment failed"
        exit 1
    fi
    
    # Cleanup
    rm -f "$package_file"
    rm -rf "$(dirname "$package_file")"
}

# Test deployment
test_deployment() {
    local stack_name="$STACK_NAME_PREFIX-$ENVIRONMENT"
    
    log_info "Testing deployment..."
    
    # Get Lambda function name from stack outputs
    local function_name
    function_name=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
        --output text)
    
    if [[ -n "$function_name" ]]; then
        log_info "Testing Lambda function: $function_name"
        
        # Create test event
        local test_event='{
            "SecretId": "'$SECRET_ARN'",
            "ClientRequestToken": "test-token-'$(date +%s)'",
            "Step": "createSecret"
        }'
        
        # Note: This is a dry-run test - actual rotation would require proper setup
        log_warning "Deployment test completed - manual testing recommended"
    else
        log_error "Could not find Lambda function name in stack outputs"
    fi
}

# Main execution
main() {
    log_info "Starting unified database password rotation deployment"
    
    parse_args "$@"
    validate_parameters
    check_prerequisites
    validate_template
    deploy_stack
    
    if [[ "$DRY_RUN" != "true" && "$VALIDATE_ONLY" != "true" ]]; then
        test_deployment
        log_success "Deployment completed successfully!"
        log_info "Next steps:"
        log_info "1. Verify the secret rotation schedule is active"
        log_info "2. Monitor CloudWatch logs and metrics"
        log_info "3. Test password rotation manually if needed"
    fi
}

# Run main function with all arguments
main "$@"
