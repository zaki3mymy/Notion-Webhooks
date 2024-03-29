import json
import urllib.request
from collections import namedtuple

import boto3
import pytest
from moto import mock_dynamodb
from pytest_mock import MockerFixture

from webhooks.lambda_handler import lambda_function

TABLE_NAME = "monitoring-table"


@pytest.fixture(autouse=True)
def setenv(monkeypatch):
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


@pytest.fixture
def lambda_context():
    lambda_context = {
        "function_name": "list_items",
        "memory_limit_in_mb": 128,
        "invoked_function_arn": "arn:aws:lambda:ap-northeast-1:123456789012:function:lambda",
        "aws_request_id": "86d7c316-9632-4d82-b4c0-12a65e521f5d",
    }

    return namedtuple("LambdaContext", lambda_context.keys())(*lambda_context.values())


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
                            "content": "テストページ",  # for ensure_ascii
                            "link": None,
                        },
                        "annotations": {
                            "bold": False,
                            "italic": False,
                            "strikethrough": False,
                            "underline": False,
                            "code": False,
                            "color": "default",
                        },
                        "plain_text": "テストページ",  # for ensure_ascii
                        "href": None,
                    },
                ],
            },
        },
        "url": "https://www.notion.so/bbb-xxxxxxxx",
        "public_url": None,
    }


def test_no_prev_info(mock_urllib_request_urlopen, lambda_context):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    mock_urlopen = mock_urllib_request_urlopen()

    # execute
    page_info = create_page_info(page_id, last_edited_time)

    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    mock_urlopen.assert_not_called

    # assert saved page
    client = boto3.client("dynamodb")
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_add_property_from_prev_info(mock_urllib_request_urlopen, lambda_context):
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    page_info["properties"]["Status"] = {  # new property
        "id": "Z%3ClH",
        "type": "status",
        "status": {
            "id": "86ddb6ec-0627-47f8-800d-b65afd28be13",
            "name": "未実施",  # for ensure_ascii
            "color": "default",
        },
    }

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {
            "properties": {
                "Status": {  # new property
                    "id": "Z%3ClH",
                    "type": "status",
                    "status": {
                        "id": "86ddb6ec-0627-47f8-800d-b65afd28be13",
                        "name": "未実施",
                        "color": "default",
                    },
                }
            }
        },
        "changed": {},
        "deleted": {},
    }
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_change_property_from_prev_info(mock_urllib_request_urlopen, lambda_context):
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    page_info["properties"]["Price"]["number"] = 5  # changed property

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
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
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_change_property_which_added_multi_select(
    mock_urllib_request_urlopen, lambda_context
):
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    page_info["properties"]["Category"]["multi_select"].append(  # changed property
        {
            "id": "t|O@",
            "name": "comic",
            "color": "yellow",
        },
    )

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {},
        "changed": {
            "old": {
                "properties": {
                    "Category": {
                        "multi_select": [],
                    },
                }
            },
            "new": {
                "properties": {
                    "Category": {
                        "multi_select": [
                            {
                                "id": "t|O@",
                                "name": "comic",
                                "color": "yellow",
                            }
                        ],
                    },
                }
            },
        },
        "deleted": {},
    }
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_change_property_which_added_multi_select_2(
    mock_urllib_request_urlopen, lambda_context
):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    prev_info = create_page_info(page_id, "2024-01-05T00:00:00.000Z")
    prev_info["properties"]["Category"]["multi_select"] = [
        {
            "id": "{Ml\\",
            "name": "anime",
            "color": "red",
        }
    ]
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    page_info["properties"]["Category"]["multi_select"].append(  # changed property
        {
            "id": "t|O@",
            "name": "comic",
            "color": "yellow",
        },
    )

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {},
        "changed": {
            "old": {
                "properties": {
                    "Category": {
                        "multi_select": [
                            {
                                "id": "{Ml\\",
                                "name": "anime",
                                "color": "red",
                            }
                        ],
                    },
                }
            },
            "new": {
                "properties": {
                    "Category": {
                        "multi_select": [
                            {
                                "id": "{Ml\\",
                                "name": "anime",
                                "color": "red",
                            },
                            {
                                "id": "t|O@",
                                "name": "comic",
                                "color": "yellow",
                            },
                        ],
                    },
                }
            },
        },
        "deleted": {},
    }
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_change_property_which_deleted_multi_select(
    mock_urllib_request_urlopen, lambda_context
):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    prev_info = create_page_info(page_id, "2024-01-05T00:00:00.000Z")
    prev_info["properties"]["Category"]["multi_select"] = [
        {
            "id": "{Ml\\",
            "name": "anime",
            "color": "red",
        }
    ]
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    page_info["properties"]["Category"]["multi_select"] = []  # changed property

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {},
        "changed": {
            "old": {
                "properties": {
                    "Category": {
                        "multi_select": [
                            {
                                "id": "{Ml\\",
                                "name": "anime",
                                "color": "red",
                            }
                        ],
                    },
                }
            },
            "new": {
                "properties": {
                    "Category": {
                        "multi_select": [],
                    },
                }
            },
        },
        "deleted": {},
    }
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_change_property_which_deleted_multi_select_2(
    mock_urllib_request_urlopen, lambda_context
):
    # prepare
    page_id = "d2b8393e-2817-4009-8311-57f9dcac0185"
    last_edited_time = "2024-01-05T03:58:00.000Z"

    prev_info = create_page_info(page_id, "2024-01-05T00:00:00.000Z")
    prev_info["properties"]["Category"]["multi_select"] = [
        {
            "id": "{Ml\\",
            "name": "anime",
            "color": "red",
        },
        {
            "id": "t|O@",
            "name": "comic",
            "color": "yellow",
        },
    ]
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    page_info["properties"]["Category"]["multi_select"] = [  # changed property
        {
            "id": "t|O@",
            "name": "comic",
            "color": "yellow",
        },
    ]

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "added": {},
        "changed": {
            "old": {
                "properties": {
                    "Category": {
                        "multi_select": [
                            {
                                "id": "{Ml\\",
                                "name": "anime",
                                "color": "red",
                            },
                            {
                                "id": "t|O@",
                                "name": "comic",
                                "color": "yellow",
                            },
                        ],
                    },
                }
            },
            "new": {
                "properties": {
                    "Category": {
                        "multi_select": [
                            {
                                "id": "t|O@",
                                "name": "comic",
                                "color": "yellow",
                            },
                        ],
                    },
                }
            },
        },
        "deleted": {},
    }
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act


def test_delete_property_from_prev_info(mock_urllib_request_urlopen, lambda_context):
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

    page_info = json.loads(json.dumps(prev_info))
    page_info["last_edited_time"] = last_edited_time
    del page_info["properties"]["Category"]  # deleted property

    # execute
    event = {
        "webhooks_url": ["https://www.example.com"],
        "page_info": page_info,
        "request_id": "20b4014c-beb2-839ce70cb-470d-13b618e",
    }
    lambda_function(event, lambda_context)

    # verify
    args = mock_urlopen.call_args.args
    act_req: urllib.request.Request = args[0]
    act_url = act_req.get_full_url()
    assert event["webhooks_url"][0] == act_url
    act_req_body = act_req.data.decode("utf-8")
    exp_req = {
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
    exp_req_body = json.dumps(exp_req, ensure_ascii=False)
    assert exp_req_body == act_req_body

    # assert saved page
    ret = client.get_item(
        TableName=TABLE_NAME,
        Key={
            "id": {"S": page_info["id"]},
        },
    )
    item = ret["Item"]
    act = item["page_info"]["S"]
    assert json.dumps(page_info, ensure_ascii=False) == act
