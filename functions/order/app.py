#import json
#import os
#import boto3
#import uuid

# boto3 is the AWS SDK for Python — how Lambda talks to SQS and SNS
#sqs = boto3.client("sqs")
#sns = boto3.client("sns")

#PAYMENT_QUEUE_URL = os.environ["PAYMENT_QUEUE_URL"]
#ORDER_TOPIC_ARN = os.environ["ORDER_TOPIC_ARN"]

#def handler(event, context):
    # Create an order (in real life this comes from an API request)
 #   order = {
  #      "orderId": str(uuid.uuid4())[:8],
   #     "item": "widget",
    #    "amount": 49.99,
    #}
    #print(f"ORDER created: {order}")

    # 1. Send the order to the PAYMENT queue (start the pipeline)
    #sqs.send_message(
     #   QueueUrl=PAYMENT_QUEUE_URL,
      #  MessageBody=json.dumps(order),
    #)
    #print(f"ORDER -> sent to payment queue")

    # 2. Publish the SAME event to SNS (fan-out to any subscribers, e.g. Audit)
    #sns.publish(
     #   TopicArn=ORDER_TOPIC_ARN,
      #  Message=json.dumps(order),
       # Subject="OrderPlaced",
    #)
   # print(f"ORDER -> published to SNS topic")

    #return {"statusCode": 200, "body": json.dumps(order)}





import json
import os
import boto3
import uuid

sqs = boto3.client("sqs")
sns = boto3.client("sns")

PAYMENT_QUEUE_URL = os.environ["PAYMENT_QUEUE_URL"]
ORDER_TOPIC_ARN = os.environ["ORDER_TOPIC_ARN"]

def handler(event, context):
    # When triggered by API Gateway, the customer's data is in event["body"]
    # as a JSON string. When invoked directly (no body), fall back to defaults.
    if event.get("body"):
        payload = json.loads(event["body"])
        item = payload.get("item", "widget")
        amount = payload.get("amount", 49.99)
    else:
        item, amount = "widget", 49.99

    order = {
        "orderId": str(uuid.uuid4())[:8],
        "item": item,
        "amount": amount,
    }
    print(f"ORDER created: {order}")

    # 1. Send the order to the PAYMENT queue (start the pipeline)
    sqs.send_message(
        QueueUrl=PAYMENT_QUEUE_URL,
        MessageBody=json.dumps(order),
    )
    print(f"ORDER -> sent to payment queue")

    # 2. Publish the SAME event to SNS (fan-out)
    sns.publish(
        TopicArn=ORDER_TOPIC_ARN,
        Message=json.dumps(order),
        Subject="OrderPlaced",
    )
    print(f"ORDER -> published to SNS topic")

    # Return a proper HTTP response for API Gateway
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "message": "Order received and processing",
            "order": order,
        }),
    }