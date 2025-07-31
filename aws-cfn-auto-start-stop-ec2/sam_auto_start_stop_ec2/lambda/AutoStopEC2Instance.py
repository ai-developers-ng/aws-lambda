from ec2_utils import configure_logging, get_ec2_client, get_instances_by_tag, stop_ec2_instances

def lambda_handler(event, context):
    logger = configure_logging()
    
    try:
        ec2_client = get_ec2_client()
        
        # Get running instances with AutoStop tag
        running_instances = get_instances_by_tag(
            ec2_client=ec2_client,
            tag_name='AutoStop',
            tag_values=['TRUE', 'True', 'true'],
            instance_states=['running']
        )
        
        logger.info(f"Found {len(running_instances)} running instances with AutoStop tag: {running_instances}")
        
        if running_instances:
            stop_ec2_instances(ec2_client, running_instances)
            logger.info(f"Successfully initiated stop for instances: {running_instances}")
        else:
            logger.info("No instances found in running state with AutoStop tag")
            
        return {
            'statusCode': 200,
            'body': f'Processed {len(running_instances)} instances for auto-stop'
        }
        
    except Exception as e:
        logger.error(f"Error in AutoStopEC2Instance: {str(e)}")
        raise
