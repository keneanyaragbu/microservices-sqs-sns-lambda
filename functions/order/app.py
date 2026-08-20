import json
import os
import boto3
import uuid

# boto3 is the AWS SDK for Python — how Lambda talks to SQS and SNS
sqs = boto3.client("sqs")
sns = boto3.client("sns")

PAYMENT_QUEUE_URL = os.environ["PAYMENT_QUEUE_URL"]
ORDER_TOPIC_ARN = os.environ["ORDER_TOPIC_ARN"]

def handler(event, context):
    # Create an order (in real life this comes from an API request)
    order = {
        "orderId": str(uuid.uuid4())[:8],
        "item": "widget",
        "amount": 49.99,
    }
    print(f"ORDER created: {order}")

    # 1. Send the order to the PAYMENT queue (start the pipeline)
    sqs.send_message(
        QueueUrl=PAYMENT_QUEUE_URL,
        MessageBody=json.dumps(order),
    )
    print(f"ORDER -> sent to payment queue")

    # 2. Publish the SAME event to SNS (fan-out to any subscribers, e.g. Audit)
    sns.publish(
        TopicArn=ORDER_TOPIC_ARN,
        Message=json.dumps(order),
        Subject="OrderPlaced",
    )
    print(f"ORDER -> published to SNS topic")

    return {"statusCode": 200, "body": json.dumps(order)}
