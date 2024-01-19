import json
import os
from collections import defaultdict
from typing import Dict, List

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent
from aws_lambda_powertools.utilities.typing import LambdaContext

if os.getenv("LOGLEVEL"):
    log_level = os.getenv("LOGLEVEL")
else:
    log_level = "INFO"
logger = Logger()
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
        url_list = r["webhooks_url"]["SS"]
        id_url_dict[database_id] = url_list

    return id_url_dict


@logger.inject_lambda_context
def lambda_function(event: EventBridgeEvent, context: LambdaContext):
    logger.structure_logs(append=True, request_id=context.aws_request_id)

    logger.info("event: %s", event)
    user_id = event["user_id"]
    lambda_name = os.environ["LAMBDA_NAME_MONITORING"]

    id_url_dict = _get_database_id_url_dict(user_id)

    client = boto3.client("lambda")
    for database_id, url_list in id_url_dict.items():
        next_event = {
            "database_id": database_id,
            "webhooks_url": url_list,
            "request_id": context.aws_request_id,
        }
        logger.debug("invoke with: %s", next_event)

        client.invoke(
            FunctionName=lambda_name,
            InvocationType="Event",
            Payload=json.dumps(next_event),
        )
