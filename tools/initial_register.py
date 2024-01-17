import os

import tqdm
from common import Logic, Model, Prompt


def main():
    # ask profile
    profile = Prompt.ask_profile()

    model = Model(profile)
    logic = Logic(model)

    # ask user_id
    user_id_env = os.getenv("NOTION_USER_EMAIL", "")
    user_id = Prompt.ask_user_id(user_id_env)

    # fetch database_id
    print("Fetching your registered database ID...")
    id_url_dict = logic.fetch_database_id_url(user_id)

    if id_url_dict == {}:
        print("You have no database settings.")
        print("Please register database id by using tools/manage_database_id.py")
        return

    database_id = Prompt.select_database_id(id_url_dict.keys())
    if Prompt.yes_no("Register page information in DB. OK?"):
        pages = logic.query_database(database_id)
        for page in tqdm.tqdm(pages, leave=False):
            logic.register_page_info(page)
        print("Done.")


if __name__ == "__main__":
    main()
