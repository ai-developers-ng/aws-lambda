aws cloudformation deploy \
  --template-file unified-db-rotation.yaml \
  --stack-name unified-db-rotation-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ExistingSecretArn=arn:aws:secretsmanager:us-west-2:123456789012:secret:mydb/secretname-abc123
