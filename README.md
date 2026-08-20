markdown
# Event-Driven Microservices Pipeline (AWS API Gateway · SQS · SNS · Lambda)

A customer-facing, event-driven order-processing pipeline built on AWS
serverless services and defined as infrastructure-as-code with AWS SAM.
Demonstrates the **synchronous-front / asynchronous-back** pattern: a fast
HTTP response to the customer, with resilient background processing behind it.

Features asynchronous service-to-service communication, message-loss recovery
with dead-letter queues, SNS fan-out, and an HTTP entry point via API Gateway.

## Architecture

[ Customer / curl ]
│ POST /order (HTTP)
▼
┌─────────────────┐
│ API Gateway │ synchronous front door — returns instantly
└────────┬────────┘
▼
┌─────────────────────────────────────────────┐
│ Order Function │
│ reads order, responds 200, then dispatches: │
└───────────────┬──────────────┬───────────────┘
│ │
(point-to-point) (fan-out)
│ │
┌───────▼──────┐ ┌────▼─────────┐
│ Payment Queue│ │ SNS Topic │
│ (+ DLQ) │ │ order-events │
└───────┬──────┘ └────┬─────────┘
│ │
┌─────────▼────────┐ ┌───▼──────────┐
│ Payment Function │ │ Audit Function│ (parallel,
└─────────┬────────┘ └──────────────┘ independent)
│
┌─────────▼────────┐
│ Fulfilment Queue │
│ (+ DLQ) │
└─────────┬────────┘
│
┌───────────▼──────────┐
│ Fulfilment Function │
│ order shipped ✓ │
└──────────────────────┘


- **API Gateway** exposes an HTTP endpoint so customers (or any client) place
  orders over the web. The Order function responds immediately, then hands the
  order to the async pipeline — the customer doesn't wait for processing.
- **SQS** connects the services point-to-point and decouples them: if a
  consumer is down, the message waits safely in the queue.
- **Dead-letter queues (DLQs)** catch messages that fail repeatedly. After
  `maxReceiveCount` attempts, SQS moves the message to the DLQ instead of
  losing it or retrying forever.
- **SNS** fans one order event out to multiple subscribers. The Audit function
  receives every order in parallel with, and independently of, the queue chain.
- **Lambda** functions run the processing, triggered by HTTP (API Gateway),
  SQS, and SNS events.

## Components

| Resource             | Type               | Purpose                                       |
|----------------------|--------------------|-----------------------------------------------|
| `API Gateway`        | REST API           | HTTP entry point — `POST /order`              |
| `order-function`     | Lambda (API trig)  | Accepts order, responds, dispatches to pipeline|
| `payment-function`   | Lambda (SQS trig)  | Processes payment → sends to Fulfilment queue  |
| `fulfilment-function`| Lambda (SQS trig)  | Completes/ships the order                      |
| `audit-function`     | Lambda (SNS trig)  | Logs every order via SNS fan-out               |
| `payment-queue`      | SQS + DLQ          | Between Order and Payment                      |
| `fulfilment-queue`   | SQS + DLQ          | Between Payment and Fulfilment                 |
| `order-events`       | SNS Topic          | Fan-out to subscribers                         |

All defined in a single `template.yaml` (AWS SAM → CloudFormation).

## Prerequisites

- AWS CLI configured with credentials
- AWS SAM CLI
- Docker (SAM uses it to build function packages)
- Python 3.12

## Deploy

```bash
sam build
sam deploy --guided     # first time; afterwards just: sam deploy
```

The Outputs include the API endpoint URL (`OrderApiUrl`).

## Place an order (HTTP)

```bash
curl -i -X POST https://<api-id>.execute-api.<region>.amazonaws.com/Prod/order \
  -H "Content-Type: application/json" \
  -d '{"item": "laptop", "amount": 1299.00}'
```

Returns an immediate response:

```json
{ "message": "Order received and processing", "order": { "orderId": "...", "item": "laptop", "amount": 1299.0 } }
```

The customer's item and amount flow through the whole pipeline. Watch it:

```bash
sam logs --stack-name order-pipeline --region <region> --start-time '5min ago'
```

ORDER created: {... 'item': 'laptop', 'amount': 1299.0}
ORDER -> sent to payment queue
ORDER -> published to SNS topic
PAYMENT approved for order <id>
FULFILMENT complete — order <id> shipped ✓
AUDIT log — order received via SNS fan-out: <id> (in parallel)


## Message-loss recovery demo (DLQ + redrive)

The core resilience demonstration.

1. **Break the Payment function** — add `raise Exception("simulated failure")`
   near the top of `functions/payment/app.py`, then `sam build && sam deploy`.

2. **Place an order** and watch it fail. SQS retries `maxReceiveCount` (3) times,
   then moves the message to the dead-letter queue. Confirm:

```bash
   aws sqs get-queue-attributes \
     --queue-url https://sqs.<region>.amazonaws.com/<account-id>/payment-dlq \
     --attribute-names ApproximateNumberOfMessages --region <region>
```
   `ApproximateNumberOfMessages` becomes `1` — preserved, not lost.

3. **Fix the function** (remove the exception), `sam build && sam deploy`.

4. **Redrive** the dead-lettered messages back to the source queue:

```bash
   aws sqs start-message-move-task \
     --source-arn arn:aws:sqs:<region>:<account-id>:payment-dlq \
     --region <region>
```

5. The fixed Payment function reprocesses them and the DLQ returns to `0`.

**Lifecycle demonstrated:** `fail → retry → dead-letter → fix → redrive → succeed`.

## Key design notes

- **Sync front / async back** — API Gateway gives the customer an instant
  response; SQS/SNS/Lambda do the heavy processing in the background.
- **`maxReceiveCount`** on the queue's `RedrivePolicy` sets how many failed
  deliveries trigger a move to the DLQ.
- **DLQs do not auto-return messages** — intentional. Auto-returning a failing
  message would loop forever ("poison message"). Fix the cause, then redrive.
- **VisibilityTimeout ≥ function timeout** — while a Lambda processes a message,
  SQS hides it; the hide-time must exceed the function runtime to avoid
  duplicate processing.
- **SQS vs SNS** — SQS is point-to-point (one consumer per message); SNS is
  fan-out (every subscriber gets a copy). This pipeline uses both.
- **API Gateway** is the HTTP front door for external clients. Internal steps
  are triggered by SQS/SNS events, not HTTP.

## How this maps to a full production system

This project is the **resilient async processing core** of an e-commerce
backend. A complete production system would add:

- **Frontend UI** (Angular, or a Java app on Tomcat) — the customer-facing store
  that calls this API when a customer places an order.
- **Database** (e.g. RDS/PostgreSQL) — the source of truth for the item catalog,
  prices, inventory, customers, and order records. Each service reads/writes it
  as it processes (create order → paid → shipped, decrement inventory).
- **Kubernetes cluster (EKS)** — the services can run as containers instead of
  Lambdas; the SQS/SNS pattern is identical.
- **CI/CD (Jenkins + ArgoCD GitOps)** — builds the service images, scans them,
  and deploys them to the cluster.
- **Front door** — API Gateway here; in a Kubernetes setup this role is often
  an Ingress + ALB doing the same HTTP entry and path-based routing.

Typically there are **two URLs**: the frontend URL the customer visits
(`shop.example.com`, serving the UI) and the API URL the frontend calls in the
background (`api.example.com/order`) — often unified under one domain with path
routing (`/` → UI, `/api/*` → services).

## Tear down

```bash
sam delete --stack-name order-pipeline --region <region>
```

## Tech

AWS API Gateway · AWS Lambda · Amazon SQS · Amazon SNS · AWS SAM ·
CloudFormation · Python · boto3
