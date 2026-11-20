# OGRL

OGRL (Open GRC Language) is an open language for a security program, and later a self-hosted application for running one.

A company runs one program. SOC 2, ISO 27001, HIPAA, NIST, and CMMC ask overlapping questions under different identifiers. That overlap usually lives in a vendor's private control library, so the program cannot leave the tool, and two tools cannot agree about the same evidence. OGRL publishes the library and the mapping rules. A control, a mapping, or a piece of evidence can move on its own. A tool can implement part of the model and still interoperate.

People author YAML they can review. Status is computed from implementations, parameters, fresh results, and unexpired evidence, so two dashboards reading the same bundle reach the same answer. A mapping that covers only part of a requirement says so.

The shared standard library lives in [`adversitydotdev/ogrl-library`](https://github.com/adversitydotdev/ogrl-library) (browsable at [ogrl.adversity.dev/library](https://ogrl.adversity.dev/library/)). Once an organization pulls a pinned library revision, their database is the source of truth for their program. A scheduled export writes a git snapshot, and the running tool does not read it back. A provider can publish what a service inherits, and a customer does not retype it. The same program renders to OSCAL when a government customer needs that package.

Language specifications live in the sibling `ogrl-rfcs` repository; application design docs live in this repo:

- RFC 0001: OGRL Object Model (`ogrl-rfcs/rfcs/0001-object-model.md`)
- RFC 0002: Tooling and Sources of Truth (`ogrl-rfcs/rfcs/0002-tooling.md`)
- [RFC 0003: Application Architecture](docs/rfcs/0003-application.md) (draft)
- [RFC 0004: HTTP API](docs/rfcs/0004-http-api.md) (draft), contract in [api/openapi.yaml](api/openapi.yaml)

## Estimated monthly cost

The production account in [RFC 0003](docs/rfcs/0003-application.md) is one Linux/ARM Fargate task (0.25 vCPU, 1 GB, API and web together), one single-AZ `db.t4g.micro`, 20 GB of gp3, a private S3 bucket, SSM Parameter Store, SES, and CloudWatch Logs. Figures below are AWS on-demand list prices for US East (N. Virginia) as of 9 November 2026. A month is 730 hours. The 12-month free tier is not subtracted. The two containers share one task, so vCPU and memory are billed once.

| Line | Rate | Per month |
|---|---|---|
| Fargate, 0.25 vCPU | $0.03238 per vCPU-hour | $5.91 |
| Fargate, 1 GB memory | $0.00356 per GB-hour | $2.60 |
| Public IPv4 on the task | $0.005 per hour | $3.65 |
| RDS for PostgreSQL, `db.t4g.micro` | $0.016 per hour | $11.68 |
| RDS gp3, 20 GB | $0.115 per GB-month | $2.30 |
| S3 Standard, 5 GB of evidence | $0.023 per GB-month | $0.12 |
| SSM Parameter Store, standard parameters | no charge | $0.00 |
| SES, no mail sent | $0.10 per 1,000 messages | $0.00 |
| CloudWatch Logs, under 5 GB | $0.50 per GB ingested after the included 5 GB | $0.00 |
| **Total** | | **$26.26** |

That total is the idle bill: the task and the database run all month, evidence is about 5 GB, and mail, logs, and data transfer stay inside the included amounts. The task and the database are in the same availability zone. Automated backups up to the 20 GB volume are included.

A model provider's token bill is separate. So is data transfer out past 100 GB ($0.09 per GB), backup storage past 20 GB, and mail once SES sends. The template creates the image repositories; storage there is $0.10 per GB-month and is not in the total above.

That account is [deploy/aws/template.yaml](deploy/aws/template.yaml). The first apply leaves the tasks off, so the bill is the database until images are pushed and `EnableServices` is set to true: about $13.98 of the $26.26. The same list rates price the steps past that:

| Change | Added per month |
|---|---|
| `EnableJobService` at `small` | $12.16, the second task ($8.51) and its public IPv4 ($3.65) |
| `EnableLoadBalancer` | $23.73 before any traffic: the balancer at $0.0225 per hour ($16.43) and a public IPv4 in each of two zones ($7.30). LCUs are $0.008 per LCU-hour on top. |
| `EnableNatGateway` | $36.50 before any data: the gateway at $0.045 per hour ($32.85) and its public IPv4 ($3.65). Data through it is $0.045 per GB. Each task that moves private drops its own $3.65 address. The gateway bills even while no task is running. |
| `EnableRdsProxy` | $22.30 for a `db.t4g.micro`: $0.015 per vCPU-hour and that class has 2 vCPUs ($21.90), plus $0.40 for the Secrets Manager secret the proxy requires. It bills whether or not a task is connected. |
| `EnableQueue` | $0 at one worker. SQS includes 1 million requests a month, and a long poll every 20 seconds stays under that. After the free tier, requests are $0.40 per million. |

`TaskSize` and `DatabaseInstanceClass` move the two lines already in the table. `medium` is the next task size, 0.5 vCPU and 2 GB.

```
aws ssm put-parameter \
  --name /ogrl/ogrl/database/password \
  --type SecureString \
  --value 'replace-with-at-least-16-characters'

aws cloudformation deploy \
  --template-file deploy/aws/template.yaml \
  --stack-name ogrl \
  --capabilities CAPABILITY_IAM
```

The password cannot contain a slash, an at-sign, a quote, or a space. The stack name `ogrl` is the path on the log groups and the SSM prefix. After rotating the password, deploy again with `DatabasePasswordVersion` set to the new SSM version so the database picks it up.

## Standard Library & CLI Toolchain

Catalog import, strict YAML 1.2 linting/formatting, bundle packing, and OSCAL 1.2.3 rendering are provided by [`adversitydotdev/ogrl-rs`](https://github.com/adversitydotdev/ogrl-rs) (consumed in-process via the `ogrl-rs` Python wheel and available as the standalone `ogrl` CLI).

```bash
# Regenerate pinned NIST SP 800-53 Rev 5 and SP 800-171 Rev 3 catalogs (with assessment objectives)
ogrl import nist --out ../ogrl-library/library

# Validate strict YAML 1.2 authoring rules and RFC 0001 §7.20 constraints
ogrl lint ../ogrl-library/library --profile library
```

By default, `OGRL_LIBRARY_REPO` pulls from `https://github.com/adversitydotdev/ogrl-library` (or uses a local `../ogrl-library/library` checkout during development).
