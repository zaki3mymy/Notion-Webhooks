import json
import os
from collections import defaultdict
from logging import getLogger
from typing import Dict, List

import boto3

if os.getenv("LOGLEVEL"):
    log_level = os.getenv("LOGLEVEL")
else:
    log_level = "INFO"
logger = getLogger(__name__)
logger.setLevel(log_level)


def _get_database_id_url_dict(user_id: str) -> Dict[str, List[str]]:
    client = boto3.client("dynamodb")
    result = client.query(
        TableName=os.environ["TABLE_NAME"],
        KeyConditionExpression="user_id = :user_id",
        ExpressionAttributeValues={":user_id": {"S": user_id}},
    )
    logger.debug("query result: %s", result)

    id_url_dict = defaultdict(list)
    for r in result["Items"]:
        database_id = r["database_id"]["S"]
        url = r["webhooks_url"]["S"]
        id_url_dict[database_id].append(url)

    return id_url_dict


def lambda_function(event, context):
    logger.info("event: %s", event)
    user_id = event["user_id"]
    lambda_name = os.environ["LAMBDA_NAME_MONITORING"]

    id_url_dict = _get_database_id_url_dict(user_id)

    client = boto3.client("lambda")
    for database_id, url_list in id_url_dict.items():
        next_event = {
            "database_id": database_id,
            "webhooks_url": url_list,
        }
        logger.debug("invoke with: %s", next_event)

        client.invoke(
            FunctionName=lambda_name,
            InvocationType="Event",
            Payload=json.dumps(next_event),
        )
