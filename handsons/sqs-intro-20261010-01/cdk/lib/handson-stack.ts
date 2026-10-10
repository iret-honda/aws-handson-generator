import * as cdk from 'aws-cdk-lib';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

export interface HandsonStackProps extends cdk.StackProps {
  readonly jobId: string;
}

// 可視性タイムアウトの既定値(秒)。SQS の既定値と同じ30秒。
const DEFAULT_VISIBILITY_TIMEOUT_SECONDS = 30;

export class HandsonStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: HandsonStackProps) {
    super(scope, id, props);

    // 第4章で `-c visibilityTimeoutSeconds=10` を渡して値を変える。指定がなければ30秒。
    const visibilityTimeoutSeconds = parseVisibilityTimeout(
      this.node.tryGetContext('visibilityTimeoutSeconds'),
    );

    // 標準キュー。暗号化は SSE-SQS(SQS 管理キー)を明示し、KMS キーは作らない。
    // 可視性タイムアウトは既定値でも明示して、`cdk diff` で 30 -> 10 の変化が見えるようにする。
    const queue = new sqs.Queue(this, 'Queue', {
      queueName: `handson-${props.jobId}-queue`,
      visibilityTimeout: cdk.Duration.seconds(visibilityTimeoutSeconds),
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new cdk.CfnOutput(this, 'QueueUrl', { value: queue.queueUrl });
    new cdk.CfnOutput(this, 'QueueName', { value: queue.queueName });
  }
}

function parseVisibilityTimeout(raw: unknown): number {
  if (raw === undefined || raw === null || raw === '') {
    return DEFAULT_VISIBILITY_TIMEOUT_SECONDS;
  }
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 0 || value > 43200) {
    throw new Error('-c visibilityTimeoutSeconds=<0〜43200 の整数> を指定してください');
  }
  return value;
}
