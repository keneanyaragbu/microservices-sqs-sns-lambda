import json

def handler(event, context):
    for record in event["Records"]:
        order = json.loads(record["body"])
        print(f"FULFILMENT processing order: {order['orderId']}")

        # (real life: ship the item, update inventory)
        print(f"FULFILMENT complete — order {order['orderId']} shipped ✓")
