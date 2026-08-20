import json
import os
import boto3

sqs = boto3.client("sqs")
FULFILMENT_QUEUE_URL = os.environ["FULFILMENT_QUEUE_URL"]

def handler(event, context):
    # SQS delivers messages in event["Records"] — could be a batch
    for record in event["Records"]:
        order = json.loads(record["body"])
        print(f"PAYMENT processing order: {order['orderId']}")
        #raise Exception("SIMULATED payment failure!")   # ← ADD THIS LINE

        # (real life: charge a card here)
        print(f"PAYMENT approved for order {order['orderId']}")

        # Pass the order to the FULFILMENT queue (next step in the chain)
        sqs.send_message(
            QueueUrl=FULFILMENT_QUEUE_URL,
            MessageBody=json.dumps(order),
        )
        print(f"PAYMENT -> sent order {order['orderId']} to fulfilment queue")
