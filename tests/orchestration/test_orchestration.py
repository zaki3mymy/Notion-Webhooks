import json
from collections import namedtuple

import boto3
import pytest
from moto import mock_dynamodb
from pytest_mock import MockerFixture

from orchestration.lambda_handler import lambda_function

TABLE_NAME = "database-id-table"
LAMBDA_NAME_MONITORING = "monitoring-lambda"


@pytest.fixture(autouse=True)
def setenv(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("LAMBDA_NAME_MONITORING", LAMBDA_NAME_MONITORING)

    # Lambda default env
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def mock_dynamodb_table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    with mock_dynamodb():
        client = boto3.client("dynamodb")
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "database_id", "AttributeType": "S"},
                # {"AttributeName": "webhooks_url", "AttributeType": "S"},
            ],
            KeySchema=[
                # DynamoDB has only two keys, partition key and sort key
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "database_id", "KeyType": "RANGE"},
                # {"AttributeName": "webhooks_url", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield


@pytest.fixture()
def mock_lambda_client(monkeypatch, mocker: MockerFixture):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    # Test with a simple Mock.
    # mock_lambda(from moto) is too long time when it do invoke.
    mock_client = mocker.MagicMock()
    dynamodb_client = boto3.client("dynamodb")

    def _wrapper(args):
        if args == "dynamodb":
            return dynamodb_client
        elif args == "lambda":
            return mock_client
        else:
            raise NotImplementedError

    mocker.patch("boto3.client", side_effect=_wrapper)

    return mock_client


def add_record(user_id, database_id, url_list):
    client = boto3.client("dynamodb")
    client.put_item(
        TableName=TABLE_NAME,
        Item={
            "user_id": {"S": user_id},
            "database_id": {"S": database_id},
            "webhooks_url": {"SS": url_list},
        },
    )


@pytest.fixture
def lambda_context():
    lambda_context = {
        "function_name": "list_items",
        "memory_limit_in_mb": 128,
        "invoked_function_arn": "arn:aws:lambda:ap-northeast-1:123456789012:function:lambda",
        "aws_request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }

    return namedtuple("LambdaContext", lambda_context.keys())(*lambda_context.values())


def test_one_database_id_one_url(mock_lambda_client, lambda_context):
    # prepare
    add_record("user01@example.com", "D001", ["https://www.example01.com"])

    # execute
    event = {"user_id": "user01@example.com"}
    lambda_function(event, lambda_context)

    # verify
    exp = json.dumps(
        {
            "database_id": "D001",
            "webhooks_url": [
                "https://www.example01.com",
            ],
            "request_id": lambda_context.aws_request_id,
        }
    )
    mock_lambda_client.invoke.assert_called_once_with(
        FunctionName=LAMBDA_NAME_MONITORING,
        InvocationType="Event",
        Payload=exp,
    )


def test_one_database_id_two_url(mock_lambda_client, lambda_context):
    # prepare
    add_record(
        "user01@example.com",
        "D001",
        ["https://www.example01.com", "https://www.example02.com"],
    )

    # execute
    event = {"user_id": "user01@example.com"}
    lambda_function(event, lambda_context)

    # verify
    exp = json.dumps(
        {
            "database_id": "D001",
            "webhooks_url": [
                "https://www.example01.com",
                "https://www.example02.com",
            ],
            "request_id": lambda_context.aws_request_id,
        }
    )
    mock_lambda_client.invoke.assert_called_once_with(
        FunctionName=LAMBDA_NAME_MONITORING,
        InvocationType="Event",
        Payload=exp,
    )


def test_two_database_id_two_url(mock_lambda_client, lambda_context):
    # prepare
    add_record("user01@example.com", "D001", ["https://www.example01.com"])
    add_record("user01@example.com", "D002", ["https://www.example02.com"])

    # execute
    event = {"user_id": "user01@example.com"}
    lambda_function(event, lambda_context)

    # verify
    call_args_list = mock_lambda_client.invoke.call_args_list
    kwargs = call_args_list[0].kwargs
    exp = {
        "FunctionName": LAMBDA_NAME_MONITORING,
        "InvocationType": "Event",
        "Payload": json.dumps(
            {
                "database_id": "D001",
                "webhooks_url": [
                    "https://www.example01.com",
                ],
                "request_id": lambda_context.aws_request_id,
            }
        ),
    }
    assert exp == kwargs
    kwargs = call_args_list[1].kwargs
    exp = {
        "FunctionName": LAMBDA_NAME_MONITORING,
        "InvocationType": "Event",
        "Payload": json.dumps(
            {
                "database_id": "D002",
                "webhooks_url": [
                    "https://www.example02.com",
                ],
                "request_id": lambda_context.aws_request_id,
            }
        ),
    }
    assert exp == kwargs
