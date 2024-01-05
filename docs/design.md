# Design notes

## Data definition

Dynamodb stores the individual [Page][notion-api-1] object acquired in [Notion API (Query A database)][notion-api-2].
The object has `id` as the primary key as follows.

```json
{
    "object": "page",
    "id": "59833787-2cf9-4fdf-8782-e53db20768a5",
    "created_time": "2022-03-01T19:05:00.000Z",
    "last_edited_time": "2022-07-06T20:25:00.000Z",
    ...
}
```


## Sequence

```mermaid
sequenceDiagram
    autonumber

    box rgb(255, 153, 0) AWS
    participant EB as EventBridge
    participant L1 as Lambda<br>monitoring
    participant L2 as Lambda<br>webhooks
    participant DynamoDB
    end
    box rgb(255, 255, 255) Notion
    participant Notion as Notion API
    end
    participant Other System

    EB -) L1: Invoke every 1 minute

    activate L1
    L1 ->>+ Notion: Get pages whose last_edited_time is after the [current date - 1 minute]
    Notion -->>- L1: List of pages

    loop Number of pages
        L1 -) L2: Invoke with page information
    end
    deactivate L1

    activate L2
    L2 ->>+ DynamoDB: Get previous page information
    DynamoDB -->>- L2: Previous page information
    L2 ->> L2: Take a difference in page information
    L2 -) Other System: Notification the difference
    L2 -) DynamoDB: Update page information
    deactivate L2
```


## Interface

### Lambda(monitoring) --> Lambda(webhooks)

The `event` object sent from Lambda (monitoring) to Lambda (webhooks) is the [Page][notion-api-1] object.
See [Data definition](#data-definition).


### Lambda(webhooks) --> Other System

The POST data sent from Lambda (webhooks) to Other System is as follows.

| No. | name | description |
| --- | ---- | ----------- |
| 1   | id   | Page ID     |
| 2   | last_edited_time | The datetime when the page was updated |
| 3   | added | Properties added to the database |
| 4   | updated | The part where there was a difference in the page |
| 5   | deleted | Properties deleted from the database |

No.3 to 5 is part of [Page][notion-api-1] objects.

For example...
```json
{
    "id": "59833787-2cf9-4fdf-8782-e53db20768a5",
    "last_edited_time": "2022-07-06T20:25:00.000Z",
    "added": {
        "properties": {
            "Due date": {
                "id": "M%3BBw",
                "type": "date",
                "date": {
                    "start": "2023-02-23",
                    "end": null,
                    "time_zone": null
                }
            }
        }
    },
    "updated": {
        "icon": {
            "type": "emoji",
            "emoji": "🐞"
        },
        "properties": {
            "Due date": {
                "id": "M%3BBw",
                "type": "date",
                "date": {
                    "start": "2023-02-23",
                    "end": null,
                    "time_zone": null
                }
            }
        }
    },
    "deleted": {
        "Status": {
            "id": "Z%3ClH",
            "type": "status",
            "status": {
                "id": "86ddb6ec-0627-47f8-800d-b65afd28be13",
                "name": "Not started",
                "color": "default"
            }
        }
    }
}
```


[notion-api-1]: https://developers.notion.com/reference/page
[notion-api-2]: https://developers.notion.com/reference/post-database-query
