import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { existsSync } from 'fs';

export interface CustomizedProps extends cdk.StackProps {
  projectName: string;
  intervalMinutes: number;
  logLevel: string;
  notionSecretKey: string | undefined;
  notionUserId: string | undefined,
}

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CustomizedProps) {
    super(scope, id, props);

    // Confirmation of environment variables
    if (props.notionSecretKey == undefined) {
      throw new Error("Environmental variable NOTION_SECRET_KEY is not set.");
    }
    if (props.notionUserId == undefined) {
      throw new Error("Environmental variable NOTION_USER_EMAIL is not set.");
    }

    // Check the existence of dependency libraries
    if (!existsSync("../lib/python/")) {
      throw new Error("Python's dependent library is not found. Please install into `../lib/python`.");
    }

    //////// Common
    const duration = Math.min(900, props.intervalMinutes * 60);

    // CloudWatch
    const logGroup = new logs.LogGroup(this, "log-group", {
      logGroupName: `/aws/lambda/${props.projectName}-logs`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      retention: logs.RetentionDays.ONE_YEAR,
    })

    // Lambda Layer
    const lambdaLayer = new lambda.LayerVersion(this, "lambda-layer", {
      layerVersionName: `${props.projectName}-common-layer`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      code: lambda.Code.fromAsset("../lib/"),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12]
    })

    // DynamoDB
    const dynamodbTableDatabaseId = new dynamodb.Table(this, "dynamodb-table-database-id", {
      tableName: `${props.projectName}-database-id`,
      partitionKey: {
        name: "user_id",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "database_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,  // On-demand request
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })
    const dynamodbTablePageInfo = new dynamodb.Table(this, "dynamodb-table-page-info", {
      tableName: `${props.projectName}-page-info`,
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
          resources: [dynamodbTablePageInfo.tableArn],
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
        "LOGLEVEL": props.logLevel,
        "TABLE_NAME": dynamodbTablePageInfo.tableName,
      },
      layers: [lambdaLayer],
      logGroup: logGroup,
    })

    //////// Monitoring
    // IAM
    const iamPolicyForMonitoring = new iam.Policy(this, "iam-policy-lambda-monitoring", {
      policyName: `${props.projectName}-lambda-invoke-policy`,
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
    iamRoleForMonitoring.attachInlinePolicy(iamPolicyForMonitoring);

    // Lambda
    const lambdaMonitoring = new lambda.Function(this, "lambda-monitoring", {
      functionName: `${props.projectName}-monitoring-lambda`,
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(duration),
      code: lambda.Code.fromAsset("../src/monitoring"),
      handler: "lambda_handler.lambda_function",
      role: iamRoleForMonitoring,
      environment: {
        "LOGLEVEL": props.logLevel,
        "SECRET_KEY": props.notionSecretKey,
        "INTERVAL_MINUTES": String(props.intervalMinutes),
        "LAMBDA_NAME_WEBHOOKS": lambdaWebhooks.functionName,
      },
      layers: [lambdaLayer],
      logGroup: logGroup,
    })

    //////// Orchestration
    // IAM
    const iamPolicyForOrchestration = new iam.Policy(this, "iam-policy-lambda-orchestration", {
      policyName: `${props.projectName}-lambda-invoke-policy`,
      statements: [
        new iam.PolicyStatement({
          actions: ["lambda:InvokeFunction"],
          resources: [lambdaMonitoring.functionArn],
        }),
        new iam.PolicyStatement({
          actions: [
            "dynamodb:Query",
          ],
          resources: [dynamodbTableDatabaseId.tableArn],
        })
      ]
    })
    const iamRoleForOrchestration = new iam.Role(this, "iam-role-lambda-orchestration", {
      roleName: `${props.projectName}-orchestration-lambda-role`,
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        {
          "managedPolicyArn": "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        }
      ]
    });
    iamRoleForOrchestration.attachInlinePolicy(iamPolicyForOrchestration);

    // Lambda
    const lambdaOrchestration = new lambda.Function(this, "lambda-orchestration", {
      functionName: `${props.projectName}-orchestration-lambda`,
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(duration),
      code: lambda.Code.fromAsset("../src/orchestration"),
      handler: "lambda_handler.lambda_function",
      role: iamRoleForOrchestration,
      environment: {
        "LOGLEVEL": props.logLevel,
        "TABLE_NAME": dynamodbTableDatabaseId.tableName,
        "LAMBDA_NAME_MONITORING": lambdaMonitoring.functionName,
      },
      layers: [lambdaLayer],
      logGroup: logGroup,
    })

    // EventBridge
    new events.Rule(this, "event-bridge", {
      ruleName: `${props.projectName}-schedule`,
      // Execute every 1 minute
      schedule: events.Schedule.cron({minute: `*/${props.intervalMinutes}`}),
      targets: [new targets.LambdaFunction(lambdaOrchestration, {
        event: events.RuleTargetInput.fromObject({
          user_id: props.notionUserId,
        })
      })]
    })
  }
}
