import json
import urllib.request

import boto3
import pytest
from moto import mock_dynamodb
from pytest_mock import MockerFixture

from webhooks.lambda_handler import lambda_function

INTEGRATION_URL = "https://example.com"
TABLE_NAME = "monitoring-table"


@pytest.fixture(autouse=True)
def setenv(monkeypatch):
    monkeypatch.setenv("INTEGRATION_URL", INTEGRATION_URL)
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)


@pytest.fixture(autouse=True)
def mock_dynamodb_table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    with mock_dynamodb():
        client = boto3.client("dynamodb")
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "id", "KeyType": "HASH"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield


@pytest.fixture()
def mock_urllib_request_urlopen(mocker: MockerFixture):
    def func():
        mock_read = mocker.MagicMock(
            return_value=r"{}"
        )  # The response doesn't matter, so make it {}
        mock_res = mocker.MagicMock(read=mock_read)
        mock_urlopen = mocker.MagicMock()
        mock_urlopen.return_value.__enter__.return_value = mock_res
        mocker.patch("urllib.request.urlopen", mock_urlopen)
        return mock_urlopen

    return func


def create_page_info(page_id, last_edited_time):
    return {
        "object": "page",
        "id": page_id,
        "created_time": "2024-01-02T08:11:00.000Z",
        "last_edited_time": last_edited_time,
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
                "type": "multi_select",
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


def test_no_prev_info(mock_urllib_request_urlopen):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    mock_urlopen = mock_urllib_request_urlopen()

    # execute
    event = create_page_info(page_id, last_edited_time)

    lambda_function(event, {})

    # verify
    mock_urlopen.assert_not_called

    # assert saved page
    client = boto3.client("dynamodb")
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": event["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert event == json.loads(act)


def test_add_property_from_prev_info(mock_urllib_request_urlopen):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    prev_info = create_page_info(page_id, "2024-01-05T00:00:00.000Z")
    client = boto3.client("dynamodb")
    client.put_item(
        TableName=TABLE_NAME,
        Item={
            "id": {"S": page_id},
            "last_edited_time": {"S": last_edited_time},
            "page_info": {"S": json.dumps(prev_info)},
        },
    )

    mock_urlopen = mock_urllib_request_urlopen()

    event = json.loads(json.dumps(prev_info))
    event["last_edited_time"] = last_edited_time
    event["properties"]["Status"] = {  # new property
        "id": "Z%3ClH",
        "type": "status",
        "status": {
            "id": "86ddb6ec-0627-47f8-800d-b65afd28be13",
            "name": "Not started",
            "color": "default",
        },
    }

    # execute
    lambda_function(event, {})

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_req_body = json.loads(act_req.data.decode("utf-8"))
    exp_req_body = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {
            "properties": {
                "Status": {  # new property
                    "id": "Z%3ClH",
                    "type": "status",
                    "status": {
                        "id": "86ddb6ec-0627-47f8-800d-b65afd28be13",
                        "name": "Not started",
                        "color": "default",
                    },
                }
            }
        },
        "changed": {},
        "deleted": {},
    }
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": event["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert event == json.loads(act)


def test_change_property_from_prev_info(mock_urllib_request_urlopen):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    prev_info = create_page_info(page_id, "2024-01-05T00:00:00.000Z")
    prev_info["properties"]["Price"] = {  # to change property
        "id": "BJXx",
        "type": "number",
        "number": 2.5,
    }
    client = boto3.client("dynamodb")
    client.put_item(
        TableName=TABLE_NAME,
        Item={
            "id": {"S": page_id},
            "last_edited_time": {"S": last_edited_time},
            "page_info": {"S": json.dumps(prev_info)},
        },
    )

    mock_urlopen = mock_urllib_request_urlopen()

    event = json.loads(json.dumps(prev_info))
    event["last_edited_time"] = last_edited_time
    event["properties"]["Price"]["number"] = 5  # changed property

    # execute
    lambda_function(event, {})

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_req_body = json.loads(act_req.data.decode("utf-8"))
    exp_req_body = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {},
        "changed": {
            "old": {
                "properties": {
                    "Price": {
                        "number": 2.5,
                    },
                }
            },
            "new": {
                "properties": {
                    "Price": {
                        "number": 5,
                    },
                }
            },
        },
        "deleted": {},
    }
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": event["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert event == json.loads(act)


def test_delete_property_from_prev_info(mock_urllib_request_urlopen):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    prev_info = create_page_info(page_id, "2024-01-05T00:00:00.000Z")
    client = boto3.client("dynamodb")
    client.put_item(
        TableName=TABLE_NAME,
        Item={
            "id": {"S": page_id},
            "last_edited_time": {"S": last_edited_time},
            "page_info": {"S": json.dumps(prev_info)},
        },
    )

    mock_urlopen = mock_urllib_request_urlopen()

    event = json.loads(json.dumps(prev_info))
    event["last_edited_time"] = last_edited_time
    del event["properties"]["Category"]  # deleted property

    # execute
    lambda_function(event, {})

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_req_body = json.loads(act_req.data.decode("utf-8"))
    exp_req_body = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {},
        "changed": {},
        "deleted": {
            "properties": {
                "Category": {
                    "id": "%3AaT",
                    "type": "multi_select",
                    "multi_select": [],
                },
            }
        },
    }
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": event["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert event == json.loads(act)
