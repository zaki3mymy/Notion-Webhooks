from collections import namedtuple
from typing import Dict, List
from uuid import UUID

import boto3
import questionary
from questionary import Choice

TABLE_NAME = "notion-webhooks-database-id"


class Model:
    Item = namedtuple("IdUrl", ("user_id", "database_id", "url_list"))

    def __init__(self, profile):
        if not profile:
            profile = "default"
        session = boto3.Session(profile_name=profile)
        self.client = session.client("dynamodb")

    def query_database_id(self, user_id) -> List[Item]:
        result = self.client.query(
            TableName=TABLE_NAME,
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": {"S": user_id}},
        )

        ret = []
        for r in result["Items"]:
            database_id = r["database_id"]["S"]
            url_list = r["webhooks_url"]["SS"]
            entity = Model.Item(user_id, database_id, url_list)
            ret.append(entity)
        return ret

    def register_item(self, item: Item):
        self.client.put_item(
            TableName=TABLE_NAME,
            Item={
                "user_id": {"S": item.user_id},
                "database_id": {"S": item.database_id},
                "webhooks_url": {"SS": item.url_list},
            },
        )

    def remove_item(self, user_id, database_id):
        self.client.delete_item(
            TableName=TABLE_NAME,
            Key={
                "user_id": {"S": user_id},
                "database_id": {"S": database_id},
            },
        )


class Logic:
    def __init__(self, model: Model):
        self.model = model

    @classmethod
    def validate_empty_input(cls, text):
        if len(text) == 0:
            return "Please enter a value"
        return True

    @classmethod
    def validate_database_id(cls, text):
        if len(text) == 0:
            return "Please enter a value"

        try:
            UUID(text)
        except ValueError:
            return "Invalid database ID"

        return True

    @classmethod
    def validate_url(cls, text):
        return True

    def fetch_database_id_url(self, user_id: str) -> Dict[str, List[str]]:
        result = self.model.query_database_id(user_id)
        dic = {}
        for r in result:
            dic[r.database_id] = r.url_list

        return dic

    def register(self, user_id, database_id, url_list):
        item = Model.Item(user_id, database_id, url_list)
        self.model.register_item(item)

    def remove_database(self, user_id, database_id):
        self.model.remove_item(user_id, database_id)


class Prompt:
    @classmethod
    def yes_no(cls, message) -> str:
        return questionary.select(
            message,
            choices=[
                Choice(title="yes", value=True),
                Choice(title="no", value=False),
            ],
        ).unsafe_ask()

    @classmethod
    def ask_profile(cls) -> str:
        return questionary.text("profile?").unsafe_ask()

    @classmethod
    def ask_user_id(cls, default="") -> str:
        return questionary.text(
            "user_id?", validate=Logic.validate_empty_input, default=default
        ).unsafe_ask()

    @classmethod
    def ask_database_id(cls) -> str:
        return questionary.text(
            "Input your database ID",
            validate=Logic.validate_database_id,
        ).unsafe_ask()

    @classmethod
    def ask_webhooks_url(cls) -> str:
        return questionary.text(
            "Input your webhooks url",
            validate=Logic.validate_url,
        ).unsafe_ask()

    @classmethod
    def select_operation(cls, ope_list: List[Choice]) -> str:
        return questionary.select(
            "Select what you want to do", choices=ope_list
        ).unsafe_ask()

    @classmethod
    def select_database_id(cls, database_id_list: List[str]) -> str:
        return questionary.select(
            "Select the database ID you want to operate",
            choices=database_id_list,
        ).unsafe_ask()

    @classmethod
    def select_url(cls, url_list: List[str]) -> str:
        return questionary.select(
            "Select the URL you want to operate",
            choices=url_list,
        ).unsafe_ask()
