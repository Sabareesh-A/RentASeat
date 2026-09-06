# Step 2A Deployment Notes

## Overview

The Lambda function (`RentASeat-API`, Python 3.13, x86_64) runs inside a VPC
so it can reach the private RDS PostgreSQL instance. A VPC-attached Lambda has
no outbound internet access by default.

AWS Secrets Manager's API is a public HTTPS endpoint. Reaching it from a
VPC-attached Lambda requires either a VPC Interface Endpoint (PrivateLink) or
a NAT Gateway — both carry monthly costs.

---

## Credential Resolution (temporary dev architecture)

The handler uses a two-step fallback:

```
1. DB_SECRET_ARN set?
   └─ Yes → try Secrets Manager
             ├─ Success → use credentials from secret
             └─ Failure (network unreachable) → log warning, try step 2
   └─ No  → go to step 2

2. DB_PASSWORD env var set?
   └─ Yes → use it (temporary dev fallback)
   └─ No  → raise RuntimeError, return 503
```

### Why not Secrets Manager right now?

| Option | Monthly cost | Notes |
|---|---|---|
| VPC Interface Endpoint | ~$4.70/month (1 AZ) | 94% of $5 budget — not viable |
| NAT Gateway | ~$32+/month | Way over budget |
| DB_PASSWORD env var | $0 | Temporary dev fallback only |

---

## ⚠️ Security Tradeoff of DB_PASSWORD Environment Variable

Using a Lambda environment variable for the database password is acceptable
**only** under these conditions (all of which apply here):

- No real user data is stored in the database yet.
- The Lambda function is not publicly exploitable for credential extraction.
- The environment variable is set **in the Lambda console only** — never in
  source code, git history, deployment scripts, or CI/CD pipelines.
- AWS Lambda encrypts environment variables at rest using the account's
  default KMS key.
- Access to `lambda:GetFunctionConfiguration` is treated as a sensitive
  permission (equivalent to having the password).

**This approach MUST be replaced with Secrets Manager before any real user
data is stored or the application is used beyond this student project.**

The replacement requires adding the Secrets Manager VPC Interface Endpoint
(one-time AWS console action, ~$4.70/month).

---

## Required AWS Console Steps Before Deploying

### Step 1 — Set DB_PASSWORD on the Lambda function

1. Open **Lambda → RentASeat-API → Configuration → Environment variables**
2. Click **Edit**
3. Add variable:
   - Key: `DB_PASSWORD`
   - Value: (the RDS master password — find it in Secrets Manager console,
     open the secret, click "Retrieve secret value")
4. Optionally add:
   - Key: `DB_USERNAME`
   - Value: `rentaseat_admin`
     (if omitted, the handler defaults to `rentaseat_admin`)
5. Click **Save**

**IMPORTANT:** Do not copy this password into any file, terminal history,
chat message, or code comment.

---

## Build and Deploy Steps

### Step 1 — Build the zip (run in your terminal)

```bash
cd /Users/sabareeshanil/Desktop/rideAseat/backend
chmod +x build.sh
./build.sh
```

Produces: `backend/rentaseat-lambda.zip` (~400–600 KB with all dependencies).

### Step 2 — Deploy via AWS Console

1. Open **Lambda → RentASeat-API → Code**
2. Click **Upload from → .zip file**
3. Select `backend/rentaseat-lambda.zip`
4. Click **Save**
5. Confirm handler is still set to: `lambda_function.lambda_handler`

### Step 3 — Deploy via AWS CLI (if available)

```bash
aws lambda update-function-code \
  --function-name RentASeat-API \
  --zip-file fileb://backend/rentaseat-lambda.zip \
  --region ap-south-1
```

---

## Post-deployment Tests

### Test 1 — Health check (must still pass, no credentials needed)

```bash
curl https://wmic9c9ilf.execute-api.ap-south-1.amazonaws.com/health
```

Expected:
```json
{"status": "ok", "service": "RentASeat-API", "message": "RentASeat backend is running"}
```

### Test 2 — DB health check

```bash
curl https://wmic9c9ilf.execute-api.ap-south-1.amazonaws.com/db-health
```

Expected (success):
```json
{"status": "ok", "database": "connected", "latency_ms": 42}
```

### Interpreting errors

Check CloudWatch Logs for `RentASeat-API`. Each log entry is a JSON object
with a `"message"` field.

| Log message | Cause | Fix |
|---|---|---|
| `"Secrets Manager unreachable from this VPC"` | No VPC endpoint/NAT | Expected — fallback to DB_PASSWORD |
| `"DB_PASSWORD environment variable is not set"` | DB_PASSWORD not configured | Set it in Lambda console |
| `"Database connection failed"` | Wrong password, wrong SG, wrong host | Check DB_PASSWORD value; check RDS SG |
| `"Secrets Manager error: AccessDeniedException"` | IAM role missing permission | Check Lambda execution role |
| `"ModuleNotFoundError"` | Missing dependency in zip | Re-run build.sh |

---

## Environment Variables (Lambda Configuration tab)

| Variable | Set by | Purpose |
|---|---|---|
| `DB_HOST` | Already set | RDS endpoint hostname |
| `DB_PORT` | Already set | PostgreSQL port (5432) |
| `DB_NAME` | Already set | Database name |
| `DB_SECRET_ARN` | Already set | ARN for Secrets Manager (preferred path) |
| `DB_PASSWORD` | **You must set this** | Temporary dev fallback password |
| `DB_USERNAME` | Optional | DB username (defaults to `rentaseat_admin`) |

---

## What the Lambda handler does NOT do (reserved for later steps)

- No user registration or login
- No JWT issuance or validation
- No RBAC
- No journey or booking APIs
- No database schema creation or migrations

---

## Future: Replacing DB_PASSWORD with Secrets Manager

When ready to remove the DB_PASSWORD fallback:

1. **Create a Secrets Manager VPC Interface Endpoint**
   - VPC → Endpoints → Create endpoint
   - Service: `com.amazonaws.ap-south-1.secretsmanager`
   - VPC: same VPC as Lambda
   - Subnet: same subnet(s) as Lambda
   - Security group: allow TCP 443 inbound from `RentASeat-Lambda-SG`
   - Policy: Full access (Lambda IAM role already restricts to the specific secret)

2. **Remove DB_PASSWORD from Lambda environment variables**

3. **Test /db-health** — it will now use Secrets Manager automatically
   (the fallback is only triggered when Secrets Manager raises an error)
