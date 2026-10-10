import { CfnResource, IAspect, RemovalPolicy } from 'aws-cdk-lib';
import { IConstruct } from 'constructs';

// 全リソースの削除ポリシーを DESTROY にする。ハンズオンでは後片付けでリソースを残さないことを優先する。
// S3 バケットの中身や ECR のイメージは、これだけでは消えない。各コンストラクトの autoDeleteObjects / emptyOnDelete も設定する。
export class DestroyAspect implements IAspect {
  visit(node: IConstruct): void {
    if (node instanceof CfnResource) {
      node.applyRemovalPolicy(RemovalPolicy.DESTROY);
    }
  }
}
