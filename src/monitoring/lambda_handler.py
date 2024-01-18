import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

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

ENDPOINT_ROOT = "https://api.notion.com/v1"


def _build_filter_conditions():
    now = datetime.now(timezone.utc)
    dt_end = now.replace(second=0, microsecond=0)
    interval = int(os.environ["INTERVAL_MINUTES"])
    dt_start = dt_end - timedelta(minutes=interval)

    cond = {
        "and": [
            {
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "after": dt_start.isoformat(),
                },
            },
            {
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "on_or_before": dt_end.isoformat(),
                },
            },
        ]
    }
    return cond


def query_database(database_id, filter_conditions):
    logger.debug("query_database filter conditions: %s", filter_conditions)

    url = f"{ENDPOINT_ROOT}/databases/{database_id}/query"
    logger.debug("query_database url: %s", url)

    SECRET_KEY = os.environ["SECRET_KEY"]
    headers = {
        "Authorization": f"Bearer {SECRET_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    results = []
    next_cursor = ""
    has_more = True
    while has_more:
        body = {
            "filter": filter_conditions,
            "page_size": 100,
        }
        if next_cursor:
            body["start_cursor"] = next_cursor

        # "Add connect" is required in the Notion database settings
        req = urllib.request.Request(url, json.dumps(body).encode(), headers)
        with urllib.request.urlopen(req) as res:
            body = json.load(res)

        results += body["results"]

        next_cursor = body["next_cursor"]
        has_more = body["has_more"]

    return results


def lambda_function(event, context):
    logger.info("event: %s", event)
    database_id = event["database_id"]
    webhooks_url = event["webhooks_url"]
    lambda_name = os.environ["LAMBDA_NAME_WEBHOOKS"]

    filter_conditions = _build_filter_conditions()
    results = query_database(database_id, filter_conditions)
    logger.info("pages count: %s", len(results))

    client = boto3.client("lambda")
    for r in results:
        id_ = r["id"]
        logger.info("page id: %s", id_)
        logger.debug("page: %s", r)

        next_event = {
            "webhooks_url": webhooks_url,
            "page_info": r
        }

        client.invoke(
            FunctionName=lambda_name,
            InvocationType="Event",
            Payload=json.dumps(next_event),
        )
