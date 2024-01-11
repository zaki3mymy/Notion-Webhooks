from collections import namedtuple
from enum import Enum
from typing import Dict, List
from uuid import UUID

import boto3
import questionary
from questionary import Choice

TABLE_NAME = "notion-webhooks-database-id"


class Operation(Enum):
    ADD_DATABASE = 1
    REMOVE_DATABASE = 2
    ADD_WEBHOOKS_URL = 3
    REMOVE_WEBHOOKS_URL = 4


class Model:
    IdUrl = namedtuple("IdUrl", ("user_id", "database_id", "url_list"))

    def __init__(self, profile):
        if not profile:
            profile = "default"
        session = boto3.Session(profile_name=profile)
        self.client = session.client("dynamodb")

    def query_database_id(self, user_id) -> List[IdUrl]:
        result = self.client.query(
            TableName=TABLE_NAME,
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": {"S": user_id}},
        )

        ret = []
        for r in result["Items"]:
            database_id = r["database_id"]["S"]
            url_list = r["webhooks_url"]["SS"]
            entity = Model.IdUrl(user_id, database_id, url_list)
            ret.append(entity)
        return ret

    def register_item(self, item: IdUrl):
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
            Item={
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
        item = Model.IdUrl(user_id, database_id, url_list)
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
    def ask_user_id(cls) -> str:
        return questionary.text(
            "user_id?",
            validate=Logic.validate_empty_input,
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


def main():
    # ask profile
    profile = Prompt.ask_profile()

    model = Model(profile)
    logic = Logic(model)

    # ask user_id
    user_id = Prompt.ask_user_id()

    # fetch database_id
    print("Fetching your registered database ID...")
    id_url_dict = logic.fetch_database_id_url(user_id)

    operation = {
        Operation.ADD_DATABASE: "add database",
        Operation.REMOVE_DATABASE: "remove database",
        Operation.ADD_WEBHOOKS_URL: "add webhooks url",
        Operation.REMOVE_WEBHOOKS_URL: "remove webhooks url",
    }
    ope_list = [Choice(title=v, value=k) for k, v in operation.items()]

    if id_url_dict == {}:
        print("You have no database settings.")
        database_id = Prompt.ask_database_id()
        url_list = []
        while True:
            url = Prompt.ask_webhooks_url()
            url_list.append(url)
            if Prompt.yes_no("Do you want to add more URLs?"):
                continue
            break
        print("Registering database info...")
        logic.register(user_id, database_id, url_list)
        print("Done.")
        return

    ope = Prompt.select_operation(ope_list)

    if ope == Operation.ADD_DATABASE:
        print("You have no database settings.")
        database_id = Prompt.ask_database_id()
        url_list = []
        while True:
            url = Prompt.ask_webhooks_url()
            url_list.append(url)
            if Prompt.yes_no("Do you want to add more URLs?"):
                continue
            break
        print("Registering database info...")
        logic.register(user_id, database_id, url_list)
        print("Done.")

    elif ope == Operation.REMOVE_DATABASE:
        database_id_list = id_url_dict.keys()
        database_id = Prompt.select_database_id(database_id_list)
        if Prompt.yes_no("It will be deleted. Are you really sure?"):
            print("Removing database info...")
            logic.remove_database(user_id, database_id)
            print("Done.")

    elif ope == Operation.ADD_WEBHOOKS_URL:
        database_id_list = id_url_dict.keys()
        database_id = Prompt.select_database_id(database_id_list)
        url_list = id_url_dict[database_id]
        while True:
            url = Prompt.ask_webhooks_url()
            url_list.append(url)
            if Prompt.yes_no("Do you want to add more URLs?"):
                continue
            break
        print("Update database info...")
        logic.register(user_id, database_id, url_list)
        print("Done.")

    elif ope == Operation.REMOVE_WEBHOOKS_URL:
        database_id_list = id_url_dict.keys()
        database_id = Prompt.select_database_id(database_id_list)
        url_list = id_url_dict[database_id]
        url = Prompt.select_url(url_list)
        if Prompt.yes_no("It will be deleted. Are you really sure?"):
            print("Update database info...")
            url_list.remove(url)
            logic.register(user_id, database_id, url_list)
            print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
