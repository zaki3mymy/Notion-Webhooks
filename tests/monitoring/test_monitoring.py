import json
from collections import namedtuple

import pytest
from freezegun import freeze_time
from pytest_mock import MockerFixture

from monitoring.lambda_handler import lambda_function

LAMBDA_NAME_WEBHOOKS = "webhooks-lambda"


@pytest.fixture(autouse=True)
def setenv(monkeypatch):
    monkeypatch.setenv(
        "SECRET_KEY", "secret_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    )
    monkeypatch.setenv("INTERVAL_MINUTES", "1")
    monkeypatch.setenv("LAMBDA_NAME_WEBHOOKS", LAMBDA_NAME_WEBHOOKS)


@pytest.fixture()
def mock_lambda_client(monkeypatch, mocker: MockerFixture):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    # Test with a simple Mock.
    # mock_lambda(from moto) is too long time when it do invoke.
    mock_client = mocker.MagicMock()
    mocker.patch("boto3.client", return_value=mock_client)

    return mock_client


@pytest.fixture
def lambda_context():
    lambda_context = {
        "function_name": "list_items",
        "memory_limit_in_mb": 128,
        "invoked_function_arn": "arn:aws:lambda:ap-northeast-1:123456789012:function:lambda",
        "aws_request_id": "67f67f77-c1e4-4ffa-913b-11cfe51d961d",
    }

    return namedtuple("LambdaContext", lambda_context.keys())(*lambda_context.values())


@freeze_time("2024-01-05T03:58:00Z")
def test_monitoring(mocker, mock_lambda_client, lambda_context):
    # prepare
    # mock Notion API
    body = {
        "results": [
            {
                "object": "page",
                "id": "d2b8393e-2817-4009-8311-57f9dcac0185",
                "created_time": "2024-01-02T08:11:00.000Z",
                "last_edited_time": "2024-01-05T03:58:00.000Z",
                "created_by": {
                    "object": "user",
                    "id": "ca7192dd-8e7a-4ccc-8faa-3e230d28778d",
                },
                "last_edited_by": {
                    "object": "user",
                    "id": "ca7192dd-8e7a-4ccc-8faa-3e230d28778d",
                },
                "cover": None,
                "icon": {"type": "emoji", "emoji": ""},
                "parent": {
                    "type": "database_id",
                    "database_id": "36142bf2-4820-4514-8891-12bcb8b8cf2",
                },
                "archive": False,
                "properties": {
                    "Category": {
                        "id": "%3AaT",
                        "typ": "multi_select",
                        "multi_select": [],
                    },
                    "Name": {
                        "id": "title",
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "bbb",
                                    "lin": None,
                                },
                                "annotations": {
                                    "bold": False,
                                    "italic": False,
                                    "strikethrough": False,
                                    "underline": False,
                                    "code": False,
                                    "color": "default",
                                },
                                "plain_text": "bbb",
                                "href": None,
                            },
                        ],
                    },
                },
                "url": "https://www.notion.so/bbb-xxxxxxxx",
                "public_url": None,
            }
        ],
        "next_cursor": None,
        "has_more": False,
    }
    mock_read = mocker.MagicMock(return_value=json.dumps(body))
    mock_res = mocker.MagicMock(read=mock_read)
    mock_urlopen = mocker.MagicMock()
    mock_urlopen.return_value.__enter__.return_value = mock_res
    mocker.patch("urllib.request.urlopen", mock_urlopen)

    # execute
    event = {
        "database_id": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "webhooks_url": ["https://www.example.com"],
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    exp = json.dumps(
        {
            "webhooks_url": event["webhooks_url"],
            "page_info": body["results"][0],
            "request_id": event["request_id"],
        }
    )
    mock_lambda_client.invoke.assert_called_once_with(
        FunctionName=LAMBDA_NAME_WEBHOOKS,
        InvocationType="Event",
        Payload=exp,
    )
