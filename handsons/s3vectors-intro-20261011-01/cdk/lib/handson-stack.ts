import * as cdk from 'aws-cdk-lib';
import * as s3vectors from 'aws-cdk-lib/aws-s3vectors';
import { Construct } from 'constructs';

export interface HandsonStackProps extends cdk.StackProps {
  readonly jobId: string;
}

// 埋め込みモデル(Amazon Titan Text Embeddings V2)に指定する出力次元と同じ値にする。
// 本文の環境変数 EMBED_DIM=256 と一致させること。インデックスの次元数は作成後に変えられない。
const EMBEDDING_DIMENSION = 256;

export class HandsonStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: HandsonStackProps) {
    super(scope, id, props);

    // ベクトルバケット。暗号化は指定せず、既定の SSE-S3 を使う(KMS キーは作らない)。
    // S3 Vectors には L2 コンストラクトがないため、L1(Cfn*)を使う。
    const bucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket', {
      vectorBucketName: `handson-${props.jobId}-vectors`,
    });
    bucket.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);

    // ベクトルインデックス。バケットは名前ではなく ARN(Fn::GetAtt)で参照する。
    // これで CloudFormation に「インデックス → バケット」の依存関係ができ、
    // 削除時はインデックスが先に消える(中にインデックスが残ったバケットは削除できないため)。
    const index = new s3vectors.CfnIndex(this, 'Index', {
      vectorBucketArn: bucket.attrVectorBucketArn,
      indexName: `handson-${props.jobId}-docs`,
      dataType: 'float32',
      dimension: EMBEDDING_DIMENSION,
      distanceMetric: 'cosine',
      metadataConfiguration: {
        // 本文テキストは検索結果として返すだけで、フィルタには使わない。
        nonFilterableMetadataKeys: ['source_text'],
      },
    });
    index.applyRemovalPolicy(cdk.RemovalPolicy.DESTROY);

    new cdk.CfnOutput(this, 'VectorBucketName', { value: `handson-${props.jobId}-vectors` });
    new cdk.CfnOutput(this, 'VectorBucketArn', { value: bucket.attrVectorBucketArn });
    new cdk.CfnOutput(this, 'IndexName', { value: `handson-${props.jobId}-docs` });
    new cdk.CfnOutput(this, 'IndexArn', { value: index.attrIndexArn });
  }
}
