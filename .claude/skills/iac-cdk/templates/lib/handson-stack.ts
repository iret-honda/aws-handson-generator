import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface HandsonStackProps extends cdk.StackProps {
  readonly jobId: string;
}

export class HandsonStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: HandsonStackProps) {
    super(scope, id, props);

    // リソース名は `handson-${props.jobId}-<役割>` にそろえる(本文の表記と一致させる)。
    // 例:
    // const queue = new sqs.Queue(this, 'Queue', {
    //   queueName: `handson-${props.jobId}-queue`,
    // });
    // new cdk.CfnOutput(this, 'QueueUrl', { value: queue.queueUrl });
  }
}
