import json
import os
import urllib.request
from collections import defaultdict
from logging import getLogger
from typing import Any, Dict, List, Union

import boto3
from deepdiff import DeepDiff, Delta

if os.getenv("LOGLEVEL"):
    log_level = os.getenv("LOGLEVEL")
else:
    log_level = "INFO"
logger = getLogger(__name__)
logger.setLevel(log_level)


def fetch_prev_page_info(page_id):
    client = boto3.client("dynamodb")
    ret = client.get_item(
        TableName=os.environ["TABLE_NAME"],
        Key={
            "id": {"S": page_id},
        },
    )
    if "Item" not in ret:
        return {}

    item = ret["Item"]
    page_info = item["page_info"]["S"]
    return json.loads(page_info)


def _generate_diff_dict(
    input_dict: Dict[str, Any], diff: Dict[str, Any], value_key="value"
) -> Dict[str, Any]:
    input_dict_ = json.loads(json.dumps(input_dict))
    path: List[Union[str, int]] = diff["path"]

    result = {}
    current = result
    for key in path[:-1]:
        current[key] = {}
        current = current[key]
        input_dict_ = input_dict_[key]

    current = input_dict_

    cur = result
    prev = cur
    logger.debug("cur: %s", cur)
    logger.debug("input_dict_: %s", input_dict_)
    for p in path:
        if p != path[-1]:
            prev = cur
            cur = cur[p]
            logger.debug("cur : %s", cur)
            logger.debug("prev: %s", prev)
        else:
            if isinstance(p, str):
                cur[p] = diff[value_key]
            else:
                prev_p = path[-2]
                prev[prev_p] = input_dict_
                if 0 < len(input_dict_) < p:
                    prev[prev_p][p] = diff[value_key]

    return result


def take_diff_in_page_info(prev_info, current_info):
    # Refer to https://zepworks.com/deepdiff/6.7.1/basics.html
    # and https://zepworks.com/deepdiff/6.7.1/serialization.html#delta-serialize-to-flat-dictionaries  # noqa: E501
    exclude_paths = [
        "last_edited_time",
    ]
    d_diff = DeepDiff(
        prev_info,
        current_info,
        exclude_paths=exclude_paths,
        ignore_numeric_type_changes=True,
    )
    if d_diff == {}:
        return d_diff
    diff_summary = Delta(d_diff, bidirectional=True).to_flat_dicts()
    logger.info("diff summary: %s", diff_summary)

    # diff_summary = [
    #     {
    #         "path": [path, to, item],
    #         "action": action name,
    #         "value": new value,
    #         ("old_value": old value)
    #     },
    #     ...
    # ]
    result = {
        "added": {},
        "changed": defaultdict(dict),
        "deleted": {},
    }
    for diff in diff_summary:
        dic = _generate_diff_dict(current_info, diff)
        logger.debug("diff dict: %s", dic)

        action = diff["action"]
        # added
        if action == "dictionary_item_added":
            result["added"] = result["added"] | dic

        # changed
        if action == "values_changed":
            old_dic = _generate_diff_dict(prev_info, diff, "old_value")

            result["changed"]["old"] = result["changed"]["old"] | old_dic
            result["changed"]["new"] = result["changed"]["new"] | dic
        elif action in ["iterable_item_added", "iterable_item_removed"]:
            logger.debug("generate old diff dict...")
            old_dic = _generate_diff_dict(prev_info, diff, "value")

            result["changed"]["old"] = result["changed"]["old"] | old_dic
            result["changed"]["new"] = result["changed"]["new"] | dic

        # deleted
        if action == "dictionary_item_removed":
            result["deleted"] = result["deleted"] | dic

    return result


def save_page_info(page_id: str, page_info: Dict[str, Any]):
    last_edited_time = page_info["last_edited_time"]
    client = boto3.client("dynamodb")
    client.put_item(
        TableName=os.environ["TABLE_NAME"],
        Item={
            "id": {"S": page_id},
            "last_edited_time": {"S": last_edited_time},
            "page_info": {"S": json.dumps(page_info, ensure_ascii=False)},
        },
    )


def send_difference(url, body):
    logger.info("url: %s", url)
    logger.info("body: %s", body)
    headers = {
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        url, json.dumps(body, ensure_ascii=False).encode(), headers
    )
    with urllib.request.urlopen(req):
        # Ignore the response because the purpose is to send a difference.
        pass


def lambda_function(event, context):
    logger.debug("event: %s", event)

    page_id = event["id"]
    logger.info("page_id: %s", page_id)
    last_edited_time = event["last_edited_time"]

    prev_page_info = fetch_prev_page_info(page_id)
    logger.debug("prev_info: %s", prev_page_info)
    save_page_info(page_id, event)
    if prev_page_info == {}:
        # new page
        logger.info("new page: %s", page_id)
        return

    diff = take_diff_in_page_info(prev_page_info, event)
    logger.info("diff in page_info: %s", diff)

    url = os.environ["INTEGRATION_URL"]
    body = {
        "id": page_id,
        "last_edited_time": last_edited_time,
    } | diff  # '|' means "merge dictionaries"
    send_difference(url, body)
