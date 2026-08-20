markdown
# Event-Driven Microservices Pipeline (AWS SQS · SNS · Lambda)

An event-driven order-processing pipeline built on AWS serverless services,
defined as infrastructure-as-code with AWS SAM. Demonstrates asynchronous
service-to-service communication, message-loss recovery with dead-letter
queues, and SNS fan-out.

## Architecture
                ┌─────────────────────────────────────────┐
                │              Order Function              │
                │  creates order, then does TWO things:    │
                └───────────────┬──────────────┬───────────┘
                                │              │
                 (point-to-point)          (fan-out)
                                │              │
                        ┌───────▼──────┐  ┌────▼─────────┐
                        │ Payment Queue│  │  SNS Topic   │
                        │   (+ DLQ)    │  │ order-events │
                        └───────┬──────┘  └────┬─────────┘
                                │              │
                      ┌─────────▼────────┐ ┌───▼──────────┐
                      │ Payment Function │ │ Audit Function│
                      └─────────┬────────┘ │ (runs in      │
                                │          │  parallel)    │
                      ┌─────────▼────────┐ └───────────────┘
                      │ Fulfilment Queue │
                      │     (+ DLQ)      │
                      └─────────┬────────┘
                                │
                    ┌───────────▼──────────┐
                    │ Fulfilment Function  │
                    │   order shipped ✓    │
                    └──────────────────────┘

- **SQS** connects the services point-to-point: each service processes a
  message and passes the order to the next queue. Services are decoupled —
  if a consumer is down, the message waits in the queue.
- **Dead-letter queues (DLQs)** catch messages that fail repeatedly. After
  `maxReceiveCount` failed attempts, SQS moves the message to the DLQ instead
  of losing it or retrying forever.
- **SNS** fans one order event out to multiple subscribers. The Audit function
  receives every order in parallel with — and independently of — the queue
  chain.
- **Lambda** functions are triggered by the events (SQS and SNS), not by HTTP.

## Components

| Resource            | Type              | Purpose                                        |
|---------------------|-------------------|------------------------------------------------|
| `order-function`    | Lambda            | Entry point — sends to Payment queue + SNS     |
| `payment-function`  | Lambda (SQS trig) | Processes payment → sends to Fulfilment queue   |
| `fulfilment-function`| Lambda (SQS trig)| Completes/ships the order                       |
| `audit-function`    | Lambda (SNS trig) | Logs every order via SNS fan-out                |
| `payment-queue`     | SQS + DLQ         | Between Order and Payment                       |
| `fulfilment-queue`  | SQS + DLQ         | Between Payment and Fulfilment                  |
| `order-events`      | SNS Topic         | Fan-out to subscribers                          |

All defined in a single `template.yaml` (AWS SAM → CloudFormation).

## Prerequisites

- AWS CLI configured with credentials
- AWS SAM CLI
- Docker (SAM uses it to build function packages)
- Python 3.12

## Deploy

```bash
sam build
sam deploy --guided     # first time; subsequent deploys just: sam deploy
```

## Run

Invoke the entry-point function to place an order:

```bash
aws lambda invoke --function-name order-function --region us-east-1 /tmp/out.json
cat /tmp/out.json
```

Watch the pipeline process it:

```bash
sam logs --stack-name order-pipeline --region us-east-1 --start-time '5min ago'
```

Expected flow (one order):

ORDER created: <id>
ORDER -> sent to payment queue
ORDER -> published to SNS topic
PAYMENT processing order: <id>
PAYMENT approved for order <id>
PAYMENT -> sent order <id> to fulfilment queue
FULFILMENT processing order: <id>
FULFILMENT complete — order <id> shipped ✓
AUDIT log — order received via SNS fan-out: <id> (in parallel)


## Message-loss recovery demo (DLQ + redrive)

This is the core resilience demonstration.

1. **Break the Payment function** — add `raise Exception("simulated failure")`
   at the top of `functions/payment/app.py`, then `sam build && sam deploy`.

2. **Send an order** and watch it fail. SQS retries it `maxReceiveCount` (3)
   times, then moves it to the dead-letter queue. Confirm the message landed:

```bash
   aws sqs get-queue-attributes \
     --queue-url https://sqs.<region>.amazonaws.com/<account-id>/payment-dlq \
     --attribute-names ApproximateNumberOfMessages --region us-east-1
```
   `ApproximateNumberOfMessages` becomes `1` — the failed message is preserved,
   not lost.

3. **Fix the function** (remove the exception), `sam build && sam deploy`.

4. **Redrive** the dead-lettered messages back to the source queue:

```bash
   aws sqs start-message-move-task \
     --source-arn arn:aws:sqs:<region>:<account-id>:payment-dlq \
     --region us-east-1
```

5. The now-fixed Payment function reprocesses the recovered messages and the
   DLQ returns to `0`.

**Lifecycle demonstrated:** `fail → retry → dead-letter → fix → redrive → succeed`.

## Key design notes

- **`maxReceiveCount`** on the queue's `RedrivePolicy` sets how many failed
  deliveries trigger a move to the DLQ.
- **DLQs do not auto-return messages** — this is intentional. Auto-returning a
  failing message would loop forever ("poison message"). You fix the cause,
  then redrive.
- **VisibilityTimeout ≥ function timeout** — while a Lambda processes a message,
  SQS hides it; the hide-time must exceed the function runtime to avoid
  duplicate processing.
- **SQS vs SNS** — SQS is point-to-point (one consumer per message); SNS is
  fan-out (every subscriber gets a copy). This pipeline uses both.
- **No API Gateway** — the functions are triggered by internal events (SQS/SNS),
  not HTTP requests. API Gateway would only be added to expose an HTTP entry
  point for external clients.

## Tear down

```bash
sam delete --stack-name order-pipeline --region us-east-1
```

## Tech

AWS Lambda · Amazon SQS · Amazon SNS · AWS SAM · CloudFormation · Python · boto3
