#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { HandsonStack } from '../lib/handson-stack';
import { DestroyAspect } from '../lib/destroy-aspect';

const app = new cdk.App();

// jobId は必須。リソース名と handson-job-id タグに使う(後片付けの確認はこのタグで行う)。
const jobId: string | undefined = app.node.tryGetContext('jobId');
if (!jobId || !/^[a-z0-9][a-z0-9-]{0,39}$/.test(jobId)) {
  throw new Error('-c jobId=<英小文字・数字・ハイフン、40文字以内> を指定してください');
}

new HandsonStack(app, `Handson-${jobId}`, {
  jobId,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});

cdk.Tags.of(app).add('handson-job-id', jobId);
cdk.Aspects.of(app).add(new DestroyAspect());
