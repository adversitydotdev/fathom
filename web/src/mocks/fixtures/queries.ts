import type { Operation, QueryDefinition } from "@/lib/api/types";

/**
 * Query sources (RFC 0006 over OpenAPI, RFC 0007 over Smithy) in mock mode.
 *
 * `apiOperations` stands in for each integration's bundled API model: what search and
 * describe return, plus `sample`, the raw items a dry run projects. The real server
 * validates with the SDK; the mock handlers apply a small subset of the same rules.
 */
export type MockOperation = Operation & {
  sample: Record<string, unknown>[];
  /** Per bound value, for for_each: other sample items, or the vendor error code the call fails with. */
  sampleBy?: Record<string, Record<string, unknown>[] | { error: string }>;
};

const OKTA = "dev.adversity.okta";
const AWS = "dev.adversity.aws";

export const queryModels: Record<string, "openapi" | "smithy"> = { [OKTA]: "openapi", [AWS]: "smithy" };

const f = (path: string, type: string, items = "", description?: string) => ({
  path,
  type,
  items,
  ...(description ? { description } : {}),
});

export const apiOperations: Record<string, MockOperation[]> = {
  [OKTA]: [
    {
      id: "listApplications",
      method: "GET",
      path: "/api/v1/apps",
      summary: "List all applications",
      queryable: true,
      parameters: [
        { name: "filter", in: "query", required: false, type: "string", description: "A filter expression, such as status eq \"ACTIVE\"." },
        { name: "limit", in: "query", required: false, type: "integer" },
      ],
      items: "",
      fields: [
        f("id", "string"),
        f("label", "string", "", "The name users see."),
        f("status", "string"),
        f("signOnMode", "string", "", "BOOKMARK, SAML_2_0, OPENID_CONNECT, and others."),
        f("created", "string"),
        f("visibility", "object"),
        f("visibility.hide.web", "boolean"),
      ],
      sample: [
        { id: "0oa1slack", label: "Slack", status: "ACTIVE", signOnMode: "SAML_2_0", created: "2023-02-01T10:00:00.000Z", visibility: { hide: { web: false } } },
        { id: "0oa2jira", label: "Jira", status: "ACTIVE", signOnMode: "OPENID_CONNECT", created: "2023-05-11T09:30:00.000Z", visibility: { hide: { web: false } } },
        { id: "0oa3wiki", label: "Team wiki", status: "ACTIVE", signOnMode: "BOOKMARK", created: "2024-01-20T14:12:00.000Z", visibility: { hide: { web: true } } },
      ],
    },
    {
      id: "listPolicies",
      method: "GET",
      path: "/api/v1/policies",
      summary: "List all policies of a type",
      queryable: true,
      parameters: [{ name: "type", in: "query", required: true, type: "string", description: "PASSWORD, OKTA_SIGN_ON, MFA_ENROLL, and others." }],
      items: "",
      fields: [
        f("id", "string"),
        f("name", "string"),
        f("status", "string"),
        f("priority", "integer"),
        f("settings.password.complexity.minLength", "integer"),
        f("settings.password.age.maxAgeDays", "integer"),
      ],
      sample: [
        { id: "00p1default", name: "Default Policy", status: "ACTIVE", priority: 2, settings: { password: { complexity: { minLength: 8 }, age: { maxAgeDays: 0 } } } },
        { id: "00p2admins", name: "Administrators", status: "ACTIVE", priority: 1, settings: { password: { complexity: { minLength: 14 }, age: { maxAgeDays: 90 } } } },
      ],
    },
    {
      id: "listGroups",
      method: "GET",
      path: "/api/v1/groups",
      summary: "List all groups",
      queryable: true,
      parameters: [{ name: "search", in: "query", required: false, type: "string" }],
      items: "",
      fields: [f("id", "string"), f("type", "string"), f("profile.name", "string"), f("profile.description", "string")],
      sample: [
        { id: "00g1eng", type: "OKTA_GROUP", profile: { name: "Engineering", description: "All engineers" } },
        { id: "00g2admins", type: "OKTA_GROUP", profile: { name: "Okta admins" } },
      ],
    },
    {
      id: "listGroupUsers",
      method: "GET",
      path: "/api/v1/groups/{groupId}/users",
      summary: "List all member users of a group",
      queryable: true,
      parameters: [{ name: "groupId", in: "path", required: true, type: "string" }],
      items: "",
      fields: [f("id", "string"), f("status", "string"), f("profile.login", "string"), f("lastLogin", "string")],
      sample: [{ id: "00u1ada", status: "ACTIVE", profile: { login: "ada@acme.test" }, lastLogin: "2026-11-19T08:00:00.000Z" }],
      sampleBy: {
        "00g1eng": [
          { id: "00u1ada", status: "ACTIVE", profile: { login: "ada@acme.test" }, lastLogin: "2026-11-19T08:00:00.000Z" },
          { id: "00u2ben", status: "ACTIVE", profile: { login: "ben@acme.test" }, lastLogin: "2026-11-18T08:00:00.000Z" },
        ],
        "00g2admins": [{ id: "00u4dee", status: "ACTIVE", profile: { login: "dee@acme.test" }, lastLogin: null }],
      },
    },
  ],
  [AWS]: [
    {
      id: "ec2.DescribeSecurityGroups",
      method: "POST",
      path: "/",
      summary: "Describes the specified security groups or all of your security groups.",
      protocol: "ec2Query",
      regional: true,
      queryable: true,
      parameters: [
        { name: "Filters", in: "json", required: false, type: "array of object" },
        { name: "GroupIds", in: "json", required: false, type: "array of string" },
      ],
      items: "SecurityGroups",
      fields: [
        f("Description", "string", "SecurityGroups"),
        f("GroupId", "string", "SecurityGroups"),
        f("GroupName", "string", "SecurityGroups"),
        f("IpPermissions", "array of object", "SecurityGroups", "Inbound rules."),
        f("VpcId", "string", "SecurityGroups"),
      ],
      sample: [
        { GroupId: "sg-0a1default", GroupName: "default", VpcId: "vpc-0prod", Description: "default VPC security group", IpPermissions: [] },
        { GroupId: "sg-0b2bastion", GroupName: "bastion", VpcId: "vpc-0prod", Description: "SSH from anywhere", IpPermissions: [{ FromPort: 22, IpRanges: [{ CidrIp: "0.0.0.0/0" }] }] },
      ],
    },
    {
      id: "s3.ListBuckets",
      method: "GET",
      path: "/?x-id=ListBuckets",
      summary: "Returns a list of all buckets owned by the authenticated sender of the request.",
      protocol: "restXml",
      regional: true,
      queryable: true,
      parameters: [
        { name: "BucketRegion", in: "value", required: false, type: "string" },
        { name: "Prefix", in: "value", required: false, type: "string" },
      ],
      items: "Buckets",
      fields: [
        f("BucketArn", "string", "Buckets"),
        f("BucketRegion", "string", "Buckets"),
        f("CreationDate", "string", "Buckets"),
        f("Name", "string", "Buckets"),
      ],
      sample: [
        { Name: "acme-evidence", BucketArn: "arn:aws:s3:::acme-evidence", BucketRegion: "us-east-1", CreationDate: "2022-03-04T10:00:00Z" },
        { Name: "acme-logs", BucketArn: "arn:aws:s3:::acme-logs", BucketRegion: "us-east-1", CreationDate: "2022-03-04T10:05:00Z" },
      ],
    },
    {
      id: "s3.GetBucketEncryption",
      method: "GET",
      path: "/{Bucket}?encryption",
      summary: "Returns the default encryption configuration for an Amazon S3 bucket.",
      protocol: "restXml",
      regional: true,
      queryable: true,
      parameters: [{ name: "Bucket", in: "value", required: true, type: "string" }],
      items: "",
      fields: [
        f("ServerSideEncryptionConfiguration", "object"),
        f("ServerSideEncryptionConfiguration.Rules", "array of object"),
      ],
      sample: [{ ServerSideEncryptionConfiguration: { Rules: [{ ApplyServerSideEncryptionByDefault: { SSEAlgorithm: "aws:kms" } }] } }],
      sampleBy: { "acme-logs": { error: "ServerSideEncryptionConfigurationNotFoundError" } },
    },
    {
      id: "iam.ListRoles",
      method: "POST",
      path: "/",
      summary: "Lists the IAM roles that have the specified path prefix.",
      protocol: "awsQuery",
      regional: false,
      queryable: true,
      parameters: [{ name: "PathPrefix", in: "value", required: false, type: "string" }],
      items: "Roles",
      fields: [
        f("Arn", "string", "Roles"),
        f("CreateDate", "string", "Roles"),
        f("RoleId", "string", "Roles"),
        f("RoleLastUsed", "object", "Roles"),
        f("RoleLastUsed.LastUsedDate", "string", "Roles"),
        f("RoleName", "string", "Roles"),
      ],
      sample: [
        { RoleId: "AROA1ADMIN", RoleName: "admin", Arn: "arn:aws:iam::447100000000:role/admin", CreateDate: "2021-06-01T00:00:00Z", RoleLastUsed: { LastUsedDate: "2026-11-19T08:00:00Z" } },
        { RoleId: "AROA2OLD", RoleName: "legacy-deploy", Arn: "arn:aws:iam::447100000000:role/legacy-deploy", CreateDate: "2020-01-15T00:00:00Z", RoleLastUsed: {} },
      ],
    },
  ],
};

export const queryDefinitions: QueryDefinition[] = [
  {
    id: "query--aws-security-groups",
    integration_id: AWS,
    name: "security-groups",
    version: 1,
    description: "Every security group and its inbound rules, in every connected region.",
    operation: "ec2.DescribeSecurityGroups",
    params: {},
    items: "",
    regions: "*",
    fields: { id: "GroupId", name: "GroupName", vpc: "VpcId", rules: "IpPermissions" },
    item_schema: {
      type: "object",
      required: ["id", "name", "region", "rules", "vpc"],
      properties: {
        id: { type: ["string", "null"] },
        name: { type: ["string", "null"] },
        vpc: { type: ["string", "null"] },
        rules: { type: ["array", "null"] },
        region: { type: ["string"] },
      },
    },
    created: "2026-11-02T09:00:00Z",
    created_by_ref: "party--priya-shah",
  },
];
