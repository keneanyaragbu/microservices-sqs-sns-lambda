import json

def handler(event, context):
    # SNS delivers messages in event["Records"] with a different structure than SQS
    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        print(f"AUDIT log — order received via SNS fan-out: {message['orderId']}")
