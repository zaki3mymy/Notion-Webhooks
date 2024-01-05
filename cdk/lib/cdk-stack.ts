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
}

export class CdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CustomizedProps) {
    super(scope, id, props);

    // IAM
    const iamRoleForMonitoring = new iam.Role(this, "iam-role-lambda-monitoring", {
      roleName: `${props.projectName}-monitoring-lambda-role`,
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        {
          "managedPolicyArn": "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        }
      ]
    })
    const iamRoleForWebhooks = new iam.Role(this, "iam-role-lambda-webhooks", {
      roleName: `${props.projectName}-webhooks-lambda-role`,
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        {
          "managedPolicyArn": "arn:aws:iam::aws:policy/service-role/AWSLambdaDynamoDBExecutionRole"
        }
      ]
    })

    // Lambda
    const pythonPackagePath = "../src/" + props.projectName.replace(/-/g, "_");
    const duration = Math.min(900, props.intervalMinutes * 60);

    const lambdaMonitoring = new lambda.Function(this, "lambda-monitoring", {
      functionName: `${props.projectName}-monitoring-lambda`,
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(duration),
      code: lambda.Code.fromAsset(pythonPackagePath),
      handler: "lambda_handler.lambda_function",
      role: iamRoleForMonitoring,
      environment: {
        "LOGLEVEL": "INFO",
        "SECRET_KEY": "secret_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "INTERVAL_MINUTES": String(props.intervalMinutes),
      }
    })
    const lambdaWebhooks = new lambda.Function(this, "lambda-webhooks", {
      functionName: `${props.projectName}-webhooks-lambda`,
      runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(duration),
      code: lambda.Code.fromAsset(pythonPackagePath),
      handler: "lambda_handler.lambda_function",
      role: iamRoleForWebhooks,
      environment: {
        "LOGLEVEL": "INFO",
        "INTEGRATION_URL": "https://example.com"
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

    // DynamoDB
    new dynamodb.Table(this, "monitoring-dynamodb-table", {
      tableName: `${props.projectName}-monitoring-table`,
      partitionKey: {
        name: "id",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "last_edited_time",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,  // On-demand request
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    })
  }
}
