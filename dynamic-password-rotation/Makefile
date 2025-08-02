# Makefile for Unified Database Password Rotation
# Provides convenient commands for development, testing, and deployment

.PHONY: help install install-dev test test-coverage lint format security clean deploy deploy-dev deploy-staging deploy-prod validate package

# Default target
help:
	@echo "Available commands:"
	@echo "  install          Install production dependencies"
	@echo "  install-dev      Install development and test dependencies"
	@echo "  test             Run all tests"
	@echo "  test-coverage    Run tests with coverage report"
	@echo "  lint             Run code linting"
	@echo "  format           Format code with black"
	@echo "  security         Run security checks"
	@echo "  clean            Clean up temporary files"
	@echo "  validate         Validate CloudFormation template"
	@echo "  package          Create deployment package"
	@echo "  deploy-dev       Deploy to development environment"
	@echo "  deploy-staging   Deploy to staging environment"
	@echo "  deploy-prod      Deploy to production environment"
	@echo ""
	@echo "Environment variables:"
	@echo "  AWS_REGION       AWS region (default: us-west-2)"
	@echo "  AWS_PROFILE      AWS profile to use"
	@echo "  SECRET_ARN       Secrets Manager secret ARN"
	@echo "  VPC_ID           VPC ID for Lambda deployment"
	@echo "  SUBNET_IDS       Comma-separated subnet IDs"
	@echo "  NOTIFICATION_EMAIL Email for failure notifications"

# Configuration
AWS_REGION ?= us-west-2
PYTHON := python3
PIP := pip3
VENV := venv
LAMBDA_FUNCTION := lambda-function.py
TEMPLATE_FILE := unified-db-rotation.yaml
REQUIREMENTS := requirements.txt
TEST_REQUIREMENTS := tests/requirements-test.txt

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Install production dependencies
install:
	@echo -e "$(BLUE)Installing production dependencies...$(NC)"
	$(PIP) install -r $(REQUIREMENTS)

# Install development dependencies
install-dev: install
	@echo -e "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP) install -r $(TEST_REQUIREMENTS)

# Set up virtual environment
venv:
	@echo -e "$(BLUE)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV)
	@echo -e "$(GREEN)Virtual environment created. Activate with: source $(VENV)/bin/activate$(NC)"

# Run all tests
test:
	@echo -e "$(BLUE)Running tests...$(NC)"
	$(PYTHON) -m pytest tests/ -v

# Run tests with coverage
test-coverage:
	@echo -e "$(BLUE)Running tests with coverage...$(NC)"
	$(PYTHON) -m pytest tests/ --cov=lambda_function --cov-report=html --cov-report=term
	@echo -e "$(GREEN)Coverage report generated in htmlcov/index.html$(NC)"

# Run specific test class
test-class:
	@echo -e "$(BLUE)Running specific test class...$(NC)"
	@read -p "Enter test class name (e.g., TestPasswordGeneration): " class; \
	$(PYTHON) -m pytest tests/test_rotation.py::$$class -v

# Run linting
lint:
	@echo -e "$(BLUE)Running code linting...$(NC)"
	flake8 $(LAMBDA_FUNCTION) config.py --max-line-length=100
	@echo -e "$(GREEN)Linting completed$(NC)"

# Format code
format:
	@echo -e "$(BLUE)Formatting code...$(NC)"
	black $(LAMBDA_FUNCTION) config.py --line-length=100
	@echo -e "$(GREEN)Code formatting completed$(NC)"

# Check code formatting
format-check:
	@echo -e "$(BLUE)Checking code formatting...$(NC)"
	black $(LAMBDA_FUNCTION) config.py --check --line-length=100

# Type checking
type-check:
	@echo -e "$(BLUE)Running type checks...$(NC)"
	mypy $(LAMBDA_FUNCTION) --ignore-missing-imports

# Security checks
security:
	@echo -e "$(BLUE)Running security checks...$(NC)"
	bandit -r $(LAMBDA_FUNCTION) config.py
	@echo -e "$(GREEN)Security checks completed$(NC)"

# Run all quality checks
quality: lint format-check type-check security
	@echo -e "$(GREEN)All quality checks passed$(NC)"

# Clean up temporary files
clean:
	@echo -e "$(BLUE)Cleaning up temporary files...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf .mypy_cache
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	rm -f deployment-package.zip
	@echo -e "$(GREEN)Cleanup completed$(NC)"

# Validate CloudFormation template
validate:
	@echo -e "$(BLUE)Validating CloudFormation template...$(NC)"
	aws cloudformation validate-template --template-body file://$(TEMPLATE_FILE) --region $(AWS_REGION)
	@echo -e "$(GREEN)Template validation passed$(NC)"

# Create deployment package
package:
	@echo -e "$(BLUE)Creating deployment package...$(NC)"
	rm -f deployment-package.zip
	zip -r deployment-package.zip $(LAMBDA_FUNCTION) config.py
	@if [ -f $(REQUIREMENTS) ]; then \
		echo "Installing dependencies..."; \
		pip install -r $(REQUIREMENTS) -t ./temp_deps/; \
		cd temp_deps && zip -r ../deployment-package.zip .; \
		cd .. && rm -rf temp_deps; \
	fi
	@echo -e "$(GREEN)Deployment package created: deployment-package.zip$(NC)"

# Deploy to development environment
deploy-dev:
	@echo -e "$(BLUE)Deploying to development environment...$(NC)"
	@if [ -z "$(SECRET_ARN)" ]; then \
		echo -e "$(RED)ERROR: SECRET_ARN environment variable is required$(NC)"; \
		exit 1; \
	fi
	./deploy.sh -e dev -r $(AWS_REGION) -s $(SECRET_ARN) $(if $(AWS_PROFILE),-p $(AWS_PROFILE)) $(if $(VPC_ID),-v $(VPC_ID)) $(if $(SUBNET_IDS),-n $(SUBNET_IDS))

# Deploy to staging environment
deploy-staging:
	@echo -e "$(BLUE)Deploying to staging environment...$(NC)"
	@if [ -z "$(SECRET_ARN)" ]; then \
		echo -e "$(RED)ERROR: SECRET_ARN environment variable is required$(NC)"; \
		exit 1; \
	fi
	./deploy.sh -e staging -r $(AWS_REGION) -s $(SECRET_ARN) $(if $(AWS_PROFILE),-p $(AWS_PROFILE)) $(if $(VPC_ID),-v $(VPC_ID)) $(if $(SUBNET_IDS),-n $(SUBNET_IDS)) $(if $(NOTIFICATION_EMAIL),-m $(NOTIFICATION_EMAIL))

# Deploy to production environment
deploy-prod:
	@echo -e "$(YELLOW)WARNING: Deploying to production environment$(NC)"
	@echo -e "$(YELLOW)This will affect production systems. Continue? [y/N]$(NC)"
	@read -r confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		if [ -z "$(SECRET_ARN)" ]; then \
			echo -e "$(RED)ERROR: SECRET_ARN environment variable is required$(NC)"; \
			exit 1; \
		fi; \
		./deploy.sh -e prod -r $(AWS_REGION) -s $(SECRET_ARN) $(if $(AWS_PROFILE),-p $(AWS_PROFILE)) $(if $(VPC_ID),-v $(VPC_ID)) $(if $(SUBNET_IDS),-n $(SUBNET_IDS)) $(if $(NOTIFICATION_EMAIL),-m $(NOTIFICATION_EMAIL)); \
	else \
		echo -e "$(BLUE)Deployment cancelled$(NC)"; \
	fi

# Dry run deployment
deploy-dry-run:
	@echo -e "$(BLUE)Running deployment dry run...$(NC)"
	@if [ -z "$(SECRET_ARN)" ]; then \
		echo -e "$(RED)ERROR: SECRET_ARN environment variable is required$(NC)"; \
		exit 1; \
	fi
	./deploy.sh -e dev -r $(AWS_REGION) -s $(SECRET_ARN) -d $(if $(AWS_PROFILE),-p $(AWS_PROFILE))

# Validate deployment only
deploy-validate:
	@echo -e "$(BLUE)Validating deployment configuration...$(NC)"
	@if [ -z "$(SECRET_ARN)" ]; then \
		echo -e "$(RED)ERROR: SECRET_ARN environment variable is required$(NC)"; \
		exit 1; \
	fi
	./deploy.sh -e dev -r $(AWS_REGION) -s $(SECRET_ARN) -t $(if $(AWS_PROFILE),-p $(AWS_PROFILE))

# Monitor deployment
monitor:
	@echo -e "$(BLUE)Monitoring Lambda function logs...$(NC)"
	@if [ -z "$(ENVIRONMENT)" ]; then \
		ENVIRONMENT=dev; \
	fi; \
	aws logs tail /aws/lambda/unified-db-rotation-$$ENVIRONMENT --follow --region $(AWS_REGION) $(if $(AWS_PROFILE),--profile $(AWS_PROFILE))

# Get deployment status
status:
	@echo -e "$(BLUE)Getting deployment status...$(NC)"
	@if [ -z "$(ENVIRONMENT)" ]; then \
		ENVIRONMENT=dev; \
	fi; \
	aws cloudformation describe-stacks --stack-name unified-db-rotation-$$ENVIRONMENT --region $(AWS_REGION) $(if $(AWS_PROFILE),--profile $(AWS_PROFILE)) --query 'Stacks[0].{StackStatus:StackStatus,LastUpdated:LastUpdatedTime}' --output table

# Delete stack
delete-stack:
	@echo -e "$(YELLOW)WARNING: This will delete the CloudFormation stack$(NC)"
	@if [ -z "$(ENVIRONMENT)" ]; then \
		echo -e "$(RED)ERROR: ENVIRONMENT environment variable is required$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(YELLOW)Delete $(ENVIRONMENT) environment stack? [y/N]$(NC)"
	@read -r confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		aws cloudformation delete-stack --stack-name unified-db-rotation-$(ENVIRONMENT) --region $(AWS_REGION) $(if $(AWS_PROFILE),--profile $(AWS_PROFILE)); \
		echo -e "$(GREEN)Stack deletion initiated$(NC)"; \
	else \
		echo -e "$(BLUE)Stack deletion cancelled$(NC)"; \
	fi

# Run integration tests
test-integration:
	@echo -e "$(BLUE)Running integration tests...$(NC)"
	@echo -e "$(YELLOW)Note: This requires AWS credentials and may incur charges$(NC)"
	$(PYTHON) -m pytest tests/test_rotation.py::TestIntegration -v

# Generate documentation
docs:
	@echo -e "$(BLUE)Generating documentation...$(NC)"
	@echo "Documentation is available in README.md"
	@echo "API documentation can be generated with:"
	@echo "  pydoc lambda_function"

# Show environment info
env-info:
	@echo -e "$(BLUE)Environment Information:$(NC)"
	@echo "Python version: $$($(PYTHON) --version)"
	@echo "AWS CLI version: $$(aws --version 2>&1 | head -n1)"
	@echo "Current AWS profile: $$(aws configure list | grep profile | awk '{print $$2}' || echo 'default')"
	@echo "Current AWS region: $$(aws configure get region || echo 'not set')"
	@echo "Working directory: $$(pwd)"

# Setup development environment
setup-dev: venv
	@echo -e "$(BLUE)Setting up development environment...$(NC)"
	@echo "1. Activate virtual environment: source $(VENV)/bin/activate"
	@echo "2. Install dependencies: make install-dev"
	@echo "3. Run tests: make test"
	@echo "4. Set environment variables in your shell:"
	@echo "   export SECRET_ARN='your-secret-arn'"
	@echo "   export AWS_REGION='us-west-2'"
	@echo "   export AWS_PROFILE='your-profile'"

# Pre-commit checks
pre-commit: quality test
	@echo -e "$(GREEN)Pre-commit checks passed$(NC)"

# CI/CD pipeline simulation
ci: clean install-dev quality test-coverage
	@echo -e "$(GREEN)CI pipeline completed successfully$(NC)"

# Show logs for specific environment
logs:
	@if [ -z "$(ENVIRONMENT)" ]; then \
		ENVIRONMENT=dev; \
	fi; \
	echo -e "$(BLUE)Showing logs for $(ENVIRONMENT) environment...$(NC)"; \
	aws logs describe-log-streams --log-group-name /aws/lambda/unified-db-rotation-$$ENVIRONMENT --region $(AWS_REGION) $(if $(AWS_PROFILE),--profile $(AWS_PROFILE)) --order-by LastEventTime --descending --max-items 1 --query 'logStreams[0].logStreamName' --output text | xargs -I {} aws logs get-log-events --log-group-name /aws/lambda/unified-db-rotation-$$ENVIRONMENT --log-stream-name {} --region $(AWS_REGION) $(if $(AWS_PROFILE),--profile $(AWS_PROFILE)) --query 'events[*].[timestamp,message]' --output table

# Get CloudWatch metrics
metrics:
	@if [ -z "$(ENVIRONMENT)" ]; then \
		ENVIRONMENT=dev; \
	fi; \
	echo -e "$(BLUE)Getting CloudWatch metrics for $(ENVIRONMENT) environment...$(NC)"; \
	aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Invocations --dimensions Name=FunctionName,Value=unified-db-rotation-$$ENVIRONMENT --start-time $$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) --end-time $$(date -u +%Y-%m-%dT%H:%M:%S) --period 300 --statistics Sum --region $(AWS_REGION) $(if $(AWS_PROFILE),--profile $(AWS_PROFILE)) --query 'Datapoints[*].[Timestamp,Sum]' --output table
