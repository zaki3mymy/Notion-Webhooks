import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export interface CustomizedProps extends cdk.StackProps {
  projectName: string;
  intervalMinutes: number;
  notionSecretKey: string | undefined;
}

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CustomizedProps) {
    super(scope, id, props);

    // Confirmation of environment variables
    if (props.notionSecretKey == undefined) {
      throw new Error("Environmental variable NOTION_SECRET_KEY is not set.");
    }

    //////// Common
    const duration = Math.min(900, props.intervalMinutes * 60);

    // Lambda Layer
    const lambdaLayer = new lambda.LayerVersion(this, "lambda-layer", {
      layerVersionName: `${props.projectName}-common-layer`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      code: lambda.Code.fromAsset("../lib/"),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12]
    })

    // DynamoDB
    const dynamodbTable = new dynamodb.Table(this, "monitoring-dynamodb-table", {
      tableName: `${props.projectName}-monitoring-table`,
      partitionKey: {
        name: "id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,  // On-demand request
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })

    //////// Webhooks
    // IAM
    const iamPolicyForWebhooks = new iam.Policy(this, "iam-policy-dynamodb", {
      policyName: `${props.projectName}-dynamodb-policy`,
      statements: [
        new iam.PolicyStatement({
          actions: [
            "dynamodb:GetItem",
            "dynamodb:PutItem",
          ],
          resources: [dynamodbTable.tableArn],
        })
      ]
    })
    const iamRoleForWebhooks = new iam.Role(this, "iam-role-lambda-webhooks", {
      roleName: `${props.projectName}-webhooks-lambda-role`,
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        {
          "managedPolicyArn": "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        }
      ]
    })
    iamRoleForWebhooks.attachInlinePolicy(iamPolicyForWebhooks);

    // Lambda
    const lambdaWebhooks = new lambda.Function(this, "lambda-webhooks", {
      functionName: `${props.projectName}-webhooks-lambda`,
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(duration),
      code: lambda.Code.fromAsset("../src/webhooks"),
      handler: "lambda_handler.lambda_function",
      role: iamRoleForWebhooks,
      environment: {
        "LOGLEVEL": "INFO",
        "INTEGRATION_URL": "https://example.com",
        "TABLE_NAME": dynamodbTable.tableName,
      },
      layers: [lambdaLayer]
    })

    //////// Monitoring
    // IAM
    const iamPolicyForInvoking = new iam.Policy(this, "iam-policy-lambda-invoking", {
      policyName: `${props.projectName}-invoke-policy`,
      statements: [
        new iam.PolicyStatement({
          actions: ["lambda:InvokeFunction"],
          resources: [lambdaWebhooks.functionArn],
        })
      ]
    })
    const iamRoleForMonitoring = new iam.Role(this, "iam-role-lambda-monitoring", {
      roleName: `${props.projectName}-monitoring-lambda-role`,
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        {
          "managedPolicyArn": "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        }
      ]
    });
    iamRoleForMonitoring.attachInlinePolicy(iamPolicyForInvoking);

    // Lambda
    const lambdaMonitoring = new lambda.Function(this, "lambda-monitoring", {
      functionName: `${props.projectName}-monitoring-lambda`,
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(duration),
      code: lambda.Code.fromAsset("../src/monitoring"),
      handler: "lambda_handler.lambda_function",
      role: iamRoleForMonitoring,
      environment: {
        "LOGLEVEL": "INFO",
        "SECRET_KEY": props.notionSecretKey,
        "INTERVAL_MINUTES": String(props.intervalMinutes),
        "LAMBDA_NAME_WEBHOOKS": lambdaWebhooks.functionName,
      }
    })

    // EventBridge
    new events.Rule(this, "monitoring-event-bridge", {
      ruleName: `${props.projectName}-monitoring-schedule`,
      // Execute every 1 minute
      schedule: events.Schedule.cron({minute: `*/${props.intervalMinutes}`}),
      targets: [new targets.LambdaFunction(lambdaMonitoring, {
        event: events.RuleTargetInput.fromObject({
          DATABASE_ID: "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        })
      })]
    })
  }
}
