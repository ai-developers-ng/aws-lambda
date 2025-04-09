import boto3
import json
import random
import string
import logging

import pymysql
import psycopg
import cx_Oracle

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secretsmanager = boto3.client('secretsmanager')

def lambda_handler(event, context):
    arn = event['SecretId']
    token = event['ClientRequestToken']
    step = event['Step']

    metadata = secretsmanager.describe_secret(SecretId=arn)
    if not metadata['RotationEnabled']:
        raise ValueError("Rotation not enabled")
    if token not in metadata['VersionIdsToStages'] or 'AWSPENDING' not in metadata['VersionIdsToStages'][token]:
        raise ValueError("Invalid token or stage")

    if step == "createSecret":
        create_secret(arn, token)
    elif step == "setSecret":
        set_secret(arn, token)
    elif step == "testSecret":
        pass  # optional
    elif step == "finishSecret":
        finish_secret(arn, token)

def create_secret(arn, token):
    current = secretsmanager.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    current_dict = json.loads(current['SecretString'])

    new_password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%^&*()', k=20))
    current_dict['password'] = new_password

    secretsmanager.put_secret_value(
        SecretId=arn,
        ClientRequestToken=token,
        SecretString=json.dumps(current_dict),
        VersionStages=['AWSPENDING']
    )
    logger.info(f"Created new password version for {arn}")

def set_secret(arn, token):
    pending = json.loads(secretsmanager.get_secret_value(
        SecretId=arn, VersionId=token, VersionStage="AWSPENDING"
    )['SecretString'])
    current = json.loads(secretsmanager.get_secret_value(
        SecretId=arn, VersionStage="AWSCURRENT"
    )['SecretString'])

    engine = current.get('engine', '').lower()
    logger.info(f"Rotating password for engine: {engine}")

    if engine == 'postgres' or engine == 'postgresql':
        rotate_postgres(current, pending)
    elif engine == 'mariadb' or engine == 'mysql':
        rotate_mariadb(current, pending)
    elif engine == 'oracle':
        rotate_oracle(current, pending)
    else:
        raise ValueError(f"Unsupported engine type: {engine}")

def rotate_postgres(current, pending):
    conn = psycopg.connect(
        host=current['host'],
        port=current['port'],
        user=current['username'],
        password=current['password'],
        dbname=current['dbname']
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"ALTER USER {pending['username']} WITH PASSWORD %s", (pending['password'],))
    conn.close()
    logger.info("PostgreSQL password rotated.")

def rotate_mariadb(current, pending):
    conn = pymysql.connect(
        host=current['host'],
        port=int(current['port']),
        user=current['username'],
        password=current['password'],
        database=current['dbname'],
        connect_timeout=10
    )
    with conn.cursor() as cur:
        cur.execute(f"ALTER USER '{pending['username']}'@'%' IDENTIFIED BY %s", (pending['password'],))
        conn.commit()
    conn.close()
    logger.info("MariaDB password rotated.")

def rotate_oracle(current, pending):
    dsn = cx_Oracle.makedsn(current['host'], int(current['port']), sid=current.get('sid', 'ORCL'))
    conn = cx_Oracle.connect(
        user=current['username'],
        password=current['password'],
        dsn=dsn
    )
    cur = conn.cursor()
    cur.execute(f"ALTER USER {pending['username']} IDENTIFIED BY \"{pending['password']}\"")
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Oracle password rotated.")

def finish_secret(arn, token):
    metadata = secretsmanager.describe_secret(SecretId=arn)
    current_version = [k for k, v in metadata['VersionIdsToStages'].items() if 'AWSCURRENT' in v][0]
    if current_version == token:
        return
    secretsmanager.update_secret_version_stage(
        SecretId=arn,
        VersionStage='AWSCURRENT',
        MoveToVersionId=token,
        RemoveFromVersionId=current_version
    )
    logger.info("Finished secret rotation.")
