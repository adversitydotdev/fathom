# RFC 0003: Application architecture

| | |
|---|---|
| Status | Draft |
| Spec version | 0.1.0 |
| Date | 2026-11-09 |
| Depends on | [RFC 0001](0001-object-model.md), [RFC 0002](0002-tooling.md) |

This document is the proposal for how the OpenGRC application is built. It is written so it can be edited in place. The open questions at the end are the spots most likely to move during review.

RFC 0001 is the language. RFC 0002 is which copy of an object is authoritative. This RFC is the processes that read and write those copies, the agents that write them, and the web application in front of them.

## 1. Summary

One Python kernel computes the graph. The objects are Pydantic models of the language. The CLI, the API, and the agents call that kernel. The web application is Next.js and speaks only HTTP. In production that process and the web application run as one small Fargate task in the organization's own AWS account. The repository provisions the account. The idle bill is the constraint, so the stack does not add a private network, a second service, or a database that cannot sleep.

An agent is another caller, not a layer beside the product. It uses the same functions the API uses, and it can only emit an object the kernel would accept. Status stays a function of the objects and a date. A model does not decide that a control is met.

Extensions are importers, renderers, runners, and connectors. They consume objects and produce objects. They do not replace the status rules. In-tree extensions are Python packages imported by the application. An organization-supplied runner or connector is a subprocess that speaks the JSON objects from RFC 0001.

## 2. Processes

| Process | Language | Role |
|---|---|---|
| `ogrc` | Python | Writes the exchange library in this repository. Calls the kernel and writes files. No server, and no organization database. |
| `opengrc` | Python | The API, the job runner, and the agents, in one process. The only writer of an organization's database. |
| Web application | TypeScript, Next.js | The screen. Reads and writes through the API. |

A person self-hosts `opengrc` and the web application. The CLI imports the same kernel the API imports, so the two cannot disagree about a bundle.

Organization commands on the CLI, once they exist, call the API. They do not open Postgres themselves. Two writers of the database would split the rules RFC 0002 puts in one place.

A job is the unit of work from RFC 0004: a library pull, a provider import, a test run, a render, a git export, a restore, or a connector run. The API records the job and returns 202. A shell test is a subprocess, so a long run does not hold the request open. The schedules in RFC 0002 are a loop in the process whose environment has `OPENGRC_RUN_SCHEDULER=true`. In the default deployment that is the API process. When the job service is on, the API process sets it false and the job process sets it true. The job process claims a row before it runs the row, so a second process does not take the same job. `OPENGRC_QUEUE_URL` is empty unless the queue is enabled. When it is set, the API sends the job id after it writes the row, and the scheduler process receives that message. The message does not replace the claim. A second delivery finds the row already owned. A message the worker does not delete returns after two hours, and after five returns it sits on the dead-letter queue.

`OPENGRC_PROCESS` is `api` or `jobs`. The web process reads `OPENGRC_API_ORIGIN`, which is `http://127.0.0.1:8080`, and forwards `/v1` and `/health` there. `OPENGRC_SSM_PREFIX` is the Parameter Store prefix. The database password is injected from `database/password`. A deployment that terminates TLS on the task reads `tls/certificate` and `tls/private-key`. A model key, when one is configured, is `model/api-key`. Harness values are under `harness/`.

The API is [FastAPI](https://fastapi.tiangolo.com/). It serves the Pydantic models and the routes in [RFC 0004](0004-http-api.md). The hand-written [api/openapi.yaml](../../api/openapi.yaml) is the contract the models implement.

## 3. Kernel

The kernel is a Python package. Its models are the objects in RFC 0001. It loads a bundle, checks the graph constraints, resolves parameters, and computes status for an evaluation date the caller passes in. Status is a function of the objects and that date.

The kernel does not open a network connection, a database, a shell, or a model client. HTTP, SQL, the `shell` runner, and the agents live outside it. A test of the kernel is a bundle plus a date, with no network.

`cmd/ogrc` and `internal/oscalimport` are the current NIST importer, in Go. That importer moves into the Python importer port. Until the port exists, `go run ./cmd/ogrc import` remains the way this repository is regenerated.

## 4. Agents

Agents are how the application drafts and proposes changes to a program. [Pydantic AI](https://ai.pydantic.dev/) is the agent runtime. A tool on an agent is a kernel function or an application use-case with a Pydantic input and a Pydantic output. Structured output that fails validation is not written.

The dependency runs one way. The agent package imports the kernel. The kernel does not import the agent package, and it does not know which model is configured.

An agent writes the same objects a person writes, through the same functions. There is no suggestion table. The language already has the gates:

| What the agent did | What the object records |
|---|---|
| Drafted a mapping | `review_status: draft` until a person reviews it, or a `mapping_review` accepts a library mapping. |
| Drafted an implementation narrative | The implementation stays `planned` until a person marks it `implemented`. |
| Recorded a result or evidence | A normal `result` or `evidence`, with `created_by_ref` pointing at the agent's `party`. |

`created_by_ref` is that party. The party is the agent as a member of the organization, so the history of the object says who produced it. A person accepts the work by the ordinary edit, the same way they would accept another person's draft.

Customer-facing coverage still uses reviewed mappings only. An agent cannot set a library mapping to `reviewed`. That field on a library row is read-only here, as in RFC 0004.

The gates in that table are enforced, not left to the agent's prompt. The application knows when the caller is an agent, and refuses these writes from one:

- An implementation `status` other than `planned`.
- `review_status: reviewed` on a mapping, a `mapping_review`, or `combined_with_refs`.
- An `exception`, a `finding`, a policy or procedure with `status: adopted`, or a risk with `status: accepted`.
- A `run` block on a test, or a change to one. An agent may ask for a run of a test whose `run` block a person wrote.
- A revoke.

Each of those is a person's judgment or a command that will execute. An agent drafts the object up to that line, and a person crosses it. The agent reads provider bundles, evidence, and policy text, and any of them can carry instructions meant for it. The refusals hold whatever the agent was told.

The agent reads the program through the same functions the API uses: an object, a page, and `GET /programs/{id}/status`. It does not recompute status, and it does not get a private copy of the graph.

Which model provider is configured is an operational choice of the deployment. The kernel's results do not change when the provider changes. A deployment with no model configured runs the API, the harness, and the imports. The agents are absent. The objects are the same.

## 5. Ports

The kernel calls four ports. It does not implement them. A port is a Python protocol. The packages we ship are imported by the application.

| Port | In | Out | Shipped as |
|---|---|---|---|
| Importer | Catalog or component-definition bytes | Objects | In-process. NIST catalogs first. OSCAL component definitions next. |
| Renderer | A graph and a view name | Files | In-process. The git snapshot and the OSCAL package from RFC 0002. |
| Runner | A test, an implementation, and a secret handle | A `result` and `evidence` | `shell` in-process. An organization-defined runner is a subprocess. |
| Connector | A collection job | `evidence` | Subprocess, when a connector exists. |

The secret handle names the variables from `run.env`. The runner asks the harness for values. Values are not fields on the test, which is the rule already in RFC 0001.

A runner subprocess is a different principal from the application. The harness starts it as a separate operating-system user, with an environment that holds the `run.env` values and the `OGRC_` variables and nothing else. It does not receive the database credential, the application's cloud credentials, or another test's secrets, and it cannot read the application's process environment. It writes evidence by leaving files in its scratch directory. The harness, not the script, stores them. A script that needs to reach a cloud account is given credentials for that purpose under `harness/`, scoped by the organization.

This is separation of credentials. It is not a sandbox. The script still shares the task's network and kernel, and an organization that does not trust its test authors runs the job service so the scripts are at least off the API task. Who may write a `run` block is therefore a permission in its own right, and it is one of the first the authorization design in RFC 0004 has to name.

A plugin that computed status, resolved parameters, or changed what a mapping relationship means would make two installations disagree about the same bundle. Those functions stay in the kernel. There is no registration point for them. An agent is not a fifth port. It calls the ports and the kernel. It does not replace them.

## 6. Subprocess plugins

An organization-defined runner or a connector is a separate program. `opengrc` starts it, writes a JSON request to stdin, and reads JSON objects from stdout. The request and the response use the objects from RFC 0001. The kernel validates the response with the same checks it uses on a file, and rejects a response that does not pass.

Secrets arrive as environment variables the harness sets for that process. The request names the variables. It does not carry the values.

The program can be written in any language that reads and writes JSON. A failed process, a timeout, or an object the kernel rejects becomes a `result` with `outcome: error`. The harness records that result and continues with the next test.

In-process plugins from outside this repository are out of scope. A connector the organization chose still runs beside the API, not inside its address space.

## 7. Persistence

Postgres holds the organization database from RFC 0002. Each object is stored as its canonical JSON. Columns beside that JSON are id, type, organization, and the references the API filters on. Those columns are derived from the object. A write updates the JSON and the columns together.

The tables are [SQLModel](https://sqlmodel.tiangolo.com/) models over SQLAlchemy's async engine, with the asyncpg driver. Each stored object is a row whose JSON goes in a `jsonb` column. A row model is not a kernel model. The kernel's Pydantic objects do not import SQLModel, and the row models live only in the persistence package. That package converts an object to a row and back.

An operation does not see a session or a row. It depends on a repository protocol it declares, and the Postgres repository is one implementation of that protocol. An in-memory implementation of the same protocol serves the tests.

`If-Match` is enforced in the update itself: `UPDATE ... WHERE id = :id AND modified = :expected`. An update that matches no row is 412. The check and the write are one statement, so two writers cannot both pass it.

The schema changes through [Alembic](https://alembic.sqlalchemy.org/) migrations. A migration is a file in the repository that a person reviews. The application does not create or alter tables when it starts.

Evidence bytes, policy and procedure bodies, and render files live in object storage. The API stores the object, including `resource.uri` and `resource.digest`. On AWS that storage is the S3 bucket the stack provisions.

The web application never opens Postgres. `ogrc` never opens it either. An agent reaches the database only through the application functions that write objects.

## 8. Web application

The web application is Next.js and TypeScript. It renders what the API returns. Status on the screen is the status the API computed. The browser does not recompute it. The routes are [RFC 0004](0004-http-api.md) and [api/openapi.yaml](../../api/openapi.yaml).

Components come from [Spectrum UI](https://ui.spectrumhq.in/). Spectrum is an open-source set of React components built with Next.js, Tailwind CSS, Motion, TypeScript, and shadcn/ui. We copy a component's source into the repository and adapt it. The application does not take a runtime dependency on the Spectrum package. shadcn/ui and Tailwind stay because Spectrum's components are written against them.

The first screens are the ones a program already has objects for: the system, the controls in the baseline and their computed status, an implementation, and the evidence on it. Landing pages, marketing blocks, and animated decoration wait until a screen needs them.

The web process owns the task's public port. Without a load balancer it listens on 443 and terminates TLS, so that process has to be allowed to bind 443. With a load balancer it listens on 3000 and the load balancer terminates TLS. Either way it forwards `/v1` and `/health` to the API on the same task.

A screen shows `created_by_ref` so a person can see which drafts an agent produced. Accepting a draft is the ordinary edit of that object.

## 9. Production topology

The production deployment runs in the organization's own cloud account. The repository ships the infrastructure description for that account. AWS is the first target. A second cloud is another description of the same bindings, not a fork of the application.

This is one organization's program, used by a small team, with bursts of test runs and exports. The bill that matters is the idle bill. A design that splits the API, the workers, a private network, and a database that cannot sleep costs more while it sits still than it costs while it works.

The idle pieces, at rough on-demand prices in us-east-1, are a NAT gateway at about $33 a month before any bytes, Aurora Serverless v2 at a 0.5 ACU floor of about $45 a month, RDS Proxy at about $11 a month, and each interface VPC endpoint at about $7 a month per availability zone. None of that scales the product. A compliance program does not have the traffic that pays those floors back. S3, SES, and a short Fargate task are cheap. The network and the database floor are not.

The deployed shape is one small task and one small database.

| Port | AWS binding | What it is for |
|---|---|---|
| Compute | One Fargate task, Linux/ARM, 0.25 vCPU and 1 GB to start | `opengrc` and the Next.js server, two containers in that task. The API, the scheduler, the harness, and the agents share it. ARM matches `db.t4g` and is the rate in the cost table. |
| Database | RDS for PostgreSQL, `db.t4g.micro`, one availability zone | The organization database. Raise the class when the disk or the CPU says so. |
| Object storage | One private S3 bucket | Evidence bytes, policy and procedure bodies, render files. |
| Secrets | SSM Parameter Store | The database credential, the model provider key, and the harness environment values. |
| Mail | SES | Operational mail. The domain identity is created by the stack and does not send until the organization verifies it. |
| Logs | CloudWatch Logs | The task's output, as structured JSON. Traces are off unless an endpoint is configured (section 11). |

At US East (N. Virginia) on-demand list rates on 9 November 2026, that stack is $26.26 a month while idle. The line items, the 730-hour month, and what the total leaves out are in the [README](../../README.md#estimated-monthly-cost). The same table is the number a later change to this topology has to beat.

The default has no load balancer, no NAT gateway, no RDS Proxy, no Aurora, no SQS, and no interface endpoint. The task sits in a public subnet with a public address so it can reach a git remote and a model provider. The database sits in a private subnet and accepts connections only from the task's security group. TLS terminates on the task. CloudFront and an application load balancer are upgrades, not the starting bill.

A shell test is a subprocess of that task, so the API keeps serving. Growth is a parameter on [deploy/aws/template.yaml](../../deploy/aws/template.yaml).

| What is tight | Parameter | Default |
|---|---|---|
| The task | `TaskSize` | `small`, 0.25 vCPU and 1 GB. Then `medium` (0.5 vCPU, 2 GB), `large` (1 vCPU, 2 GB), `xlarge` (2 vCPU, 4 GB), `2xlarge` (4 vCPU, 8 GB). |
| The database | `DatabaseInstanceClass`, `DatabaseAllocatedStorage` | `db.t4g.micro` and 20 GB. Storage may grow on its own up to `DatabaseMaxAllocatedStorage` (100). |
| Jobs waiting on each other | `EnableJobService` | `false`. A second task of the same image, with its own public address and still no NAT. The schedule moves to that task. |
| A public address that changes whenever the task is replaced | `EnableLoadBalancer`, `CertificateArn` | `false`. The load balancer terminates TLS and is the stable name. The task keeps a public address for git and the model provider. |
| Outbound calls should not come from the task's own address | `EnableNatGateway` | `false`. One NAT gateway. Tasks move to the private subnet. A free S3 gateway endpoint keeps evidence off the NAT. Once services are started this requires the load balancer, because the tasks no longer have public addresses. |
| Many tasks holding database connections | `EnableRdsProxy` | `false`. RDS Proxy pools connections. The proxy reads the database password from Secrets Manager, so the template copies it there. |
| A worker should be woken instead of polling | `EnableQueue` | `false`. An SQS queue and a dead-letter queue. The job row is still the record of the work. |

Raise the task and the database before adding the job task. Add the load balancer when the service needs a name that survives a replacement. The default public address is the task's, and it changes when the task is replaced.

SES is for mail the application sends: a scheduled job that failed, and an export that stopped because the remote diverged. Authentication mail uses the same port once accounts exist. The stack does not invent a second notification product. A new SES account can send only to verified addresses until AWS grants production access. The template does not request that access.

The infrastructure lives in the repository as a CloudFormation template, [deploy/aws/template.yaml](../../deploy/aws/template.yaml). Applying it provisions the network, the database, the bucket, the image repositories, the task definition, SES when a domain is set, and the IAM those need. `EnableServices` stays false until the images have been pushed, so the first apply does not start a task. It does not upload the organization's evidence, and it does not choose their model provider. Those are configuration after apply. The database password is a SecureString the operator writes at `database/password` under the stack's SSM prefix before the first apply. CloudFormation cannot create a SecureString, so it reads that parameter when it creates the database. The certificate and key for TLS on the task are `tls/certificate` and `tls/private-key` under the same prefix.

A developer still runs `opengrc` as one process against a local Postgres. The kernel tests do not need any of the cloud.

## 10. Repository layout

This layout is the target. `cmd/ogrc` and `internal/oscalimport` are the Go importer that this layout replaces.

```text
opengrc/
  kernel/        # models, graph, parameters, status
  importer/      # importer port and the NIST importer
  renderer/      # git snapshot and OSCAL
  runner/        # shell runner
  agent/         # Pydantic AI agents and their tools
  persistence/   # SQLModel rows, Postgres repositories, Alembic migrations
  telemetry.py   # the only module that imports logfire
  api/           # FastAPI application, including the in-process job runner
  cli/           # ogrc
web/             # Next.js application
deploy/aws/      # CloudFormation for the production topology
```

Connectors are not a directory until one exists. A subprocess connector lives in its own project.

## 11. Observability

Code that logs uses the standard library's `logging`. The kernel and the operations do not import a telemetry vendor.

Traces and logs go through the [Logfire](https://logfire.pydantic.dev/) SDK. The SDK is MIT-licensed and is built on OpenTelemetry. It instruments FastAPI, SQLAlchemy, asyncpg, httpx, and Pydantic AI, so a request, its queries, and an agent run share one trace. `opengrc/telemetry.py` is the only module that imports `logfire`. The process calls it once at startup. Removing Logfire is a change to that one module.

The Logfire SDK does not require the hosted Logfire service. Where telemetry goes is configuration:

| Setting | Where telemetry goes |
|---|---|
| Nothing set | Structured JSON on stdout, which CloudWatch Logs collects. No traces are exported. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Any OTLP backend the organization runs, such as Grafana, SigNoz, or Jaeger. |
| `LOGFIRE_TOKEN` | Hosted Logfire, for an organization that chooses to pay for it. |

The default is the first row. A collector container in the task, or an exporter that bills while idle, is an upgrade the operator turns on, like `EnableLoadBalancer`. It is not in the starting bill in section 9.

## 12. Open questions

1. **Authentication.** Accounts are still out of scope, as in RFC 0001. The API will have a boundary for the signed-in organization before any screen writes an implementation. The mechanism is a later RFC. SES is already in the stack for the day that mechanism sends mail. Until it exists, the API is not safe on a public address: creating a test and running it is command execution on the task, and nothing checks the caller. The topology in section 9 puts the task on a public address, so `EnableServices` stays false outside a private test until this is settled.
2. **Model provider.** The agent runtime is Pydantic AI, which can talk to more than one provider. Which provider a deployment uses, and whether the model runs in the organization's network, is an operational choice. It is not a kernel choice.
3. **A second cloud.** AWS is the first topology. The ports are the same on another cloud. A second CloudFormation template is worth writing when an organization asks for one, and not before.
