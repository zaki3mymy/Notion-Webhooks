# Notion-Webhooks

Notion-Webhooks notifies the Notion page change.

## Description

The motivation for this project is to notify another system for changing the Notion page. When we are using Notion in a free plan, the only action that can be handled by automation is only notification to Slack. You can also notify Teams, Discord or other tools with Notion-Webhooks.

For example, it is assumed that when the status of the page is changed to `Done`, it will notify the system that records the completed date and time.

## Architecture

Notion-Webhooks is deployed on your AWS account.
![image](./docs/assets/architecture.svg)

See the [design.md](./docs/design.md) for details.

## Requirement

Notion-Webhooks is made in Python. The dependent library is as follows.

- deepdiff 6.7.1


## Deployment

Do deployment using CDK.
You need to download the dependent library for Lambda Layer before the deployer.

We have a shell script for downloading.
If you execute it, the dependent library will be downloaded to the `./lib/python` directory.

```bash
sh download-dependencies.sh
```

### Deploy with CDK.

First, prepare CDK with `npm install`.

```bash
cd cdk
npm install
```

Once you set an environment variable, deploy with CDK!
```bash
export NOTION_USER_EMAIL=user@example.com
export NOTION_SECRET_KEY=secret_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

cdk deploy --profile <your profile>
```
