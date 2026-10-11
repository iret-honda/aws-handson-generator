import datetime as dt

import boto3
from botocore.stub import Stubber

from conftest import JOB_ID
from sandbox_runner.resources import Aws, delete_rank, kind_of

BUCKET_ARN = f"arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/handson-{JOB_ID}-vectors"
INDEX_ARN = f"{BUCKET_ARN}/index/handson-{JOB_ID}-docs"
OTHER_ARN = "arn:aws:s3vectors:ap-northeast-1:123456789012:bucket/other"
TAG = "handson-job-id"


def stubbed_aws() -> tuple[Aws, Stubber]:
    session = boto3.Session(aws_access_key_id="x", aws_secret_access_key="x", region_name="ap-northeast-1")
    aws = Aws("unused", "ap-northeast-1", session=session)
    stub = Stubber(aws.client("s3vectors"))
    stub.activate()
    return aws, stub


def test_kind_of_s3vectors():
    assert kind_of(BUCKET_ARN) == "s3vectors:bucket"
    assert kind_of(INDEX_ARN) == "s3vectors:index"
    # インデックスはバケットより先に消す
    assert delete_rank("s3vectors:index") < delete_rank("s3vectors:bucket")


def test_has_job_tag_uses_s3vectors_tags():
    aws, stub = stubbed_aws()
    stub.add_response("list_tags_for_resource", {"tags": {TAG: JOB_ID}}, {"resourceArn": INDEX_ARN})
    stub.add_response("list_tags_for_resource", {"tags": {TAG: "other-job"}}, {"resourceArn": OTHER_ARN})
    stub.add_client_error("list_tags_for_resource", "NotFoundException", http_status_code=404)
    assert aws.has_job_tag(INDEX_ARN, TAG, JOB_ID)
    assert not aws.has_job_tag(OTHER_ARN, TAG, JOB_ID)
    assert not aws.has_job_tag(BUCKET_ARN, TAG, JOB_ID)


def test_s3vectors_inventory_reads_tags_directly():
    aws, stub = stubbed_aws()
    stub.add_response("list_vector_buckets", {"vectorBuckets": [
        {"vectorBucketName": f"handson-{JOB_ID}-vectors", "vectorBucketArn": BUCKET_ARN,
         "creationTime": dt.datetime(2026, 10, 11)},
        {"vectorBucketName": "other", "vectorBucketArn": OTHER_ARN, "creationTime": dt.datetime(2026, 10, 1)},
    ]})
    stub.add_response("list_tags_for_resource", {"tags": {TAG: JOB_ID}}, {"resourceArn": BUCKET_ARN})
    stub.add_response("list_indexes", {"indexes": [
        {"vectorBucketName": f"handson-{JOB_ID}-vectors", "indexName": f"handson-{JOB_ID}-docs",
         "indexArn": INDEX_ARN, "creationTime": dt.datetime(2026, 10, 11)},
    ]}, {"vectorBucketArn": BUCKET_ARN})
    stub.add_response("list_tags_for_resource", {"tags": {TAG: JOB_ID}}, {"resourceArn": INDEX_ARN})
    stub.add_response("list_tags_for_resource", {"tags": {}}, {"resourceArn": OTHER_ARN})
    stub.add_response("list_indexes", {"indexes": []}, {"vectorBucketArn": OTHER_ARN})

    # Tagging API で既に見つかったものは重複させない
    seen = {INDEX_ARN}
    found = aws._s3vectors_inventory(TAG, JOB_ID, any_value=False, seen=seen)
    assert [(r.arn, r.kind) for r in found] == [(BUCKET_ARN, "s3vectors:bucket")]
    stub.assert_no_pending_responses()


def test_describe_s3vectors_not_found_counts_as_gone():
    aws, stub = stubbed_aws()
    stub.add_response("get_index", {"index": {
        "vectorBucketName": "bkt", "indexName": "idx", "indexArn": INDEX_ARN, "creationTime": dt.datetime(2026, 10, 11),
        "dataType": "float32", "dimension": 256, "distanceMetric": "cosine"}}, {"indexArn": INDEX_ARN})
    stub.add_client_error("get_vector_bucket", "NotFoundException", http_status_code=404)
    assert aws.describe(INDEX_ARN) == (True, "2026-10-11T00:00:00+00:00")
    assert aws.describe(BUCKET_ARN) == (False, None)


def test_delete_s3vectors_bucket_removes_indexes_first():
    aws, stub = stubbed_aws()
    stub.add_response("list_tags_for_resource", {"tags": {TAG: JOB_ID}}, {"resourceArn": BUCKET_ARN})
    stub.add_response("list_indexes", {"indexes": [
        {"vectorBucketName": "bkt", "indexName": "idx", "indexArn": INDEX_ARN, "creationTime": dt.datetime(2026, 10, 11)},
    ]}, {"vectorBucketArn": BUCKET_ARN})
    stub.add_response("delete_index", {}, {"indexArn": INDEX_ARN})
    stub.add_response("delete_vector_bucket", {}, {"vectorBucketArn": BUCKET_ARN})
    assert aws.delete(BUCKET_ARN, TAG, JOB_ID) == "deleted"
    stub.assert_no_pending_responses()
