import os
from enum import Enum

from common import Logic, Model, Prompt
from questionary import Choice


class Operation(Enum):
    ADD_DATABASE = 1
    REMOVE_DATABASE = 2
    ADD_WEBHOOKS_URL = 3
    REMOVE_WEBHOOKS_URL = 4


def main():
    # ask profile
    profile = Prompt.ask_profile()

    model = Model(profile)
    logic = Logic(model)

    # ask user_id
    user_id_env = os.getenv("NOTION_USER_EMAIL")
    user_id = Prompt.ask_user_id(user_id_env)

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
