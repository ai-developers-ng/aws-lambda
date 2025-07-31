from ec2_utils import configure_logging, get_ec2_client, get_instances_by_tag, start_ec2_instances

def lambda_handler(event, context):
    logger = configure_logging()
    
    try:
        ec2_client = get_ec2_client()
        
        # Get stopped instances with AutoStart tag
        stopped_instances = get_instances_by_tag(
            ec2_client=ec2_client,
            tag_name='AutoStart',
            tag_values=['TRUE', 'True', 'true'],
            instance_states=['stopped']
        )
        
        logger.info(f"Found {len(stopped_instances)} stopped instances with AutoStart tag: {stopped_instances}")
        
        if stopped_instances:
            start_ec2_instances(ec2_client, stopped_instances)
            logger.info(f"Successfully initiated start for instances: {stopped_instances}")
        else:
            logger.info("No instances found in stopped state with AutoStart tag")
            
        return {
            'statusCode': 200,
            'body': f'Processed {len(stopped_instances)} instances for auto-start'
        }
        
    except Exception as e:
        logger.error(f"Error in AutoStartEC2Instance: {str(e)}")
        raise
