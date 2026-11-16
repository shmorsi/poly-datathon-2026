# EPICENTRE live app: EC2 behind CloudFront (runbook)

Written Sat Nov 14 2026, hardened (an app that cannot start without a
password, and a secret origin header), and corrected to describe what the live deploy actually did (every
resource tagged, secrets that are never printed, egress narrowed to TCP 443, the macOS and zsh commands that worked,
teardown before 13:59, a Redeploy block). **Writing or editing this file creates no AWS resource.** A human runs the commands below, by hand.
Placeholders are in `<ANGLE_BRACKETS>`: no id, account number or secret is ever pasted into this file. Credentials come
from the standard chain (a temporary role); they are never pasted, logged or committed. Window: the live deploy started
**Sat Nov 14 23:55** and the app stays up until the teardown, which runs **before Mon Nov 16 13:59** (section 9 says how
the hours and the cost are counted). The permanent URL stays the GitHub Pages static demo; this app is the live,
password-protected one.

## Architecture

```
browser --HTTPS--> CloudFront (*.cloudfront.net) --HTTP :8000 + X-Origin-Verify--> EC2 t3.small (public subnet, no key pair)
                                                                  Docker: uvicorn server:app, non-root
                                                                  instance role = docs/iam/runtime-policy.json --> Bedrock
```

- HTTPS ends at CloudFront, on its own `*.cloudfront.net` name (default certificate, no domain to buy). The viewer
  protocol policy is `redirect-to-https`: a browser is only challenged on the HTTPS URL, so the viewer never sends the
  password over plain HTTP. Never `curl -u` an `http://` address.
- **Gate 1, the network.** The instance security group admits **only** the CloudFront origin-facing managed prefix list
  (`com.amazonaws.global.cloudfront.origin-facing`) on TCP 8000. No inbound 0.0.0.0/0, no port 22, no other source;
  **outbound TCP 443 only** (the default allow-everything egress rule is replaced, section 3a). The one `0.0.0.0/0` in
  the whole stack is that outbound HTTPS rule: with no NAT gateway and no VPC endpoints, the instance reaches dnf,
  GitHub, Docker Hub, PyPI, Session Manager and Bedrock over the internet on port 443, and nothing else leaves.
- **Gate 2, the secret origin header.** CloudFront adds `X-Origin-Verify: <secret>` to every request it sends to the
  instance (a `CustomHeaders` entry on the origin). The app, started with `EPICENTRE_ORIGIN_SECRET`, answers 403 to any
  request without the matching header, before it asks for a password; only `/api/health` (three booleans, no data) is
  exempt. The secret is generated on the laptop into an owner-only file, never printed, committed or logged, reaches
  the instance through the Session Manager port-forward (section 4) and is rotated at teardown.
- **Gate 3, the password.** The app asks for HTTP Basic credentials on every route except `/api/health`. The password
  is `EPICENTRE_PASSWORD`: environment only, no default, never logged, never in the image. The container starts with
  `EPICENTRE_REQUIRE_PASSWORD=1`, which makes the app refuse to start when the password is empty or unset, so it never
  comes up open by accident. CloudFront must forward the `Authorization` header (managed cache policy `CachingDisabled`
  plus managed origin request policy `AllViewer`); the smoke test in section 4 proves it with curl.
- Access to the instance is Session Manager (SSM): no SSH key, no port 22. No public S3 bucket (one private, versioned bucket keeps a
  decision record only when the investor seals one, section 11), no load balancer, no database. The container stores no
  other input (red gate 6).
- The instance role is `docs/iam/runtime-policy.json` (Bedrock InvokeModel and ApplyGuardrail only) plus the AWS
  managed policy `AmazonSSMManagedInstanceCore`.
- **Every resource carries the tag `Project=epicentre`** (the role, the instance profile, the security group and its
  rules, the instance, its volume and network interface, the distribution), and the id of each one is appended to a
  local, owner-only teardown file the moment it exists (section 2 says where). The teardown (section 7) loads that file
  and deletes only what is in it. The AWS account may hold other people's resources, for example another CloudFront
  distribution that is not ours: **never touch a resource that is not in the teardown file**, and tell ours apart by
  its comment, never by position in a list.

Two limits, said plainly. (1) The CloudFront-to-instance leg is plain HTTP on port 8000 (an AWS-to-AWS path, but not
TLS), so neither the Basic header nor the origin secret is encrypted on that leg; both are throwaways for this window
and are rotated at teardown. The origin secret can also be read by anyone who can read the distribution config (and
probably sits in the account's CloudTrail record of the create call), and both values can be read by root on the
instance (`/root/epicentre.env`, and `docker inspect`, which prints the container's environment). So the secret keeps
strangers and other CloudFront distributions out, not someone who is already inside this AWS account. (2) The prefix list admits every CloudFront
distribution in the world, not only ours: gate 2 turns a stranger's distribution away (403, before any password is
asked) and gate 3 stops everyone else. `/api/health` (three booleans, no data) is the only open route. Section 8
removes both limits.

## 1. Go / no-go

Do nothing below until the team lead has said yes in writing. Go only if all three hold:

1. The event role can create and tag EC2 instances, a security group, an IAM role with an instance profile, and a
   CloudFront distribution, and can delete all of them again. Check without creating anything (two read-only calls,
   below) and read each `EvalDecision`: every action must be `allowed`, because a refusal half way through would leave a
   half-built stack, and a refused delete would leave it running past the deadline. The simulator reads the role's own
   policies only, not organisation-level service control policies, so `allowed` here is necessary, not sufficient: the
   real proof is that each create call in sections 2 to 3 succeeds.

```bash
ROLE_ARN=<ROLE_ARN>           # the event role you are signed in as: aws sts get-caller-identity shows it
Q='EvaluationResults[].[EvalActionName,EvalDecision]'
aws iam simulate-principal-policy --policy-source-arn $ROLE_ARN --query "$Q" --output text --action-names \
  ec2:RunInstances ec2:CreateTags ec2:CreateSecurityGroup ec2:AuthorizeSecurityGroupIngress \
  ec2:AuthorizeSecurityGroupEgress ec2:RevokeSecurityGroupEgress \
  iam:CreateRole iam:TagRole iam:PutRolePolicy iam:AttachRolePolicy iam:CreateInstanceProfile iam:TagInstanceProfile \
  iam:AddRoleToInstanceProfile iam:PassRole \
  cloudfront:CreateDistributionWithTags cloudfront:TagResource cloudfront:GetCachePolicy cloudfront:GetOriginRequestPolicy \
  ssm:StartSession
aws iam simulate-principal-policy --policy-source-arn $ROLE_ARN --query "$Q" --output text --action-names \
  cloudfront:GetDistributionConfig cloudfront:UpdateDistribution cloudfront:DeleteDistribution \
  ec2:TerminateInstances ec2:DeleteSecurityGroup ec2:RevokeSecurityGroupIngress \
  iam:RemoveRoleFromInstanceProfile iam:DeleteInstanceProfile iam:DetachRolePolicy iam:DeleteRolePolicy iam:DeleteRole
```
2. Bedrock answers from this account (`python scripts/check_bedrock.py`), and the guardrail exists and is `READY`
   (`EPICENTRE_GUARDRAIL_ID`, `EPICENTRE_GUARDRAIL_VERSION`). **Guardrail version note.** Until the Sun 14:00 freeze
   publishes a numbered version, only the working copy `DRAFT` exists. The app passes the version string to
   ApplyGuardrail as it is, so it runs on `DRAFT`, and the Docker line below says `EPICENTRE_GUARDRAIL_VERSION=DRAFT`.
   Once the freeze has published the number, run the Redeploy block (section 4) with that number: it is the same line
   with one value changed, and it is the only change the app needs. Never create a second guardrail for this.
3. The cost in section 9 is accepted: about 1.10 USD of infrastructure for the whole window (Sat 23:55 to Mon 13:59,
   counted in section 9), to be checked against the dated AWS price pages (Bedrock runs are extra, and the password
   bounds them).

No-go: the demo stays local, plus the video and the GitHub Pages static demo, and the technical doc says so in one
sentence. Nothing else in the project depends on this deployment.

## 2. The local folder, the teardown file and the instance role

### 2a. One owner-only folder outside the repo, and the teardown file

Everything this runbook writes on your laptop goes into one folder, `~/.epicentre`, created owner-only (mode 700, files
600) and outside the repo, so nothing in it can be committed by accident. Two kinds of file live there: the **teardown
file** (`teardown.env`: resource ids and names only, never a secret) and, from section 3b, the two generated secrets.
After every create call below, the id is appended to the teardown file at once (`note NAME value`), so the teardown
(section 7) works even if the shell, the laptop session or your memory is gone. The same shell stays open until the end
of section 3; if it is lost, `source` the file again.

```bash
umask 077                                        # every file created below is owner-only
mkdir -p ~/.epicentre && chmod 700 ~/.epicentre
TEARDOWN=~/.epicentre/teardown.env
touch "$TEARDOWN" && chmod 600 "$TEARDOWN"
note() { printf '%s=%s\n' "$1" "$2" >> "$TEARDOWN"; }      # ids and names only: NEVER pass a secret to note
REGION=us-east-1                                 # every command below uses this region; CloudFront is global
note REGION $REGION
export AWS_PAGER=""                              # so a long answer never opens a pager
```

**Tags.** Every resource that can carry a tag is created with `Project=epicentre` (EC2 and IAM take it in the create
call; CloudFront takes it in `create-distribution-with-tags`). The tag does two jobs: a console search or
`list-tags-for-resource` finds anything this runbook made, and the evidence pack shows that the stack is ours. The
AWS-managed prefix list and the managed policies are not ours and carry nothing.

### 2b. The instance role

The role is `docs/iam/runtime-policy.json` (least privilege: `bedrock:InvokeModel` on the Sonnet profiles and
`bedrock:ApplyGuardrail` on our guardrail, nothing else) plus the AWS managed policy `AmazonSSMManagedInstanceCore`
(Session Manager, so no SSH key and no port 22). The repo copy keeps its `<ACCOUNT_ID>` and `<GUARDRAIL_ID>`
placeholders; the filled copy lives in `~/.epicentre` and is never committed. Use `${ACCOUNT_ID}` with braces: zsh (the
macOS default shell) reads `$ACCOUNT_ID:role/...` as the variable followed by a `:r` modifier and silently drops text.
Run from the repo root:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GUARDRAIL_ID=<GUARDRAIL_ID>            # printed by scripts/create_guardrail.py
sed -e "s/<ACCOUNT_ID>/${ACCOUNT_ID}/g" -e "s/<GUARDRAIL_ID>/${GUARDRAIL_ID}/g" \
    docs/iam/runtime-policy.json > ~/.epicentre/runtime-policy.filled.json
cat > ~/.epicentre/ec2-trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
aws iam create-role --role-name epicentre-runtime --tags Key=Project,Value=epicentre \
    --assume-role-policy-document file://$HOME/.epicentre/ec2-trust.json --query Role.RoleName --output text \
  && note ROLE_NAME epicentre-runtime
aws iam put-role-policy --role-name epicentre-runtime --policy-name epicentre-runtime \
    --policy-document file://$HOME/.epicentre/runtime-policy.filled.json
aws iam attach-role-policy --role-name epicentre-runtime \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam create-instance-profile --instance-profile-name epicentre-runtime --tags Key=Project,Value=epicentre \
    --query InstanceProfile.InstanceProfileName --output text \
  && note PROFILE_NAME epicentre-runtime
aws iam add-role-to-instance-profile --instance-profile-name epicentre-runtime --role-name epicentre-runtime
```

Wait about 15 seconds before section 3 (a new instance profile is not visible to EC2 at once). If the event role
refuses `iam:CreateRole`, stop: that is a no-go (section 1), not a reason to attach a broader existing role.

## 3. Launch

Amazon Linux 2023, t3.small, IMDSv2 required, no key pair, no load balancer, no public S3. The security group admits one
thing only: TCP 8000 from the CloudFront origin-facing prefix list, never 0.0.0.0/0 inbound and never a personal /32,
and lets out one thing only: TCP 443. To test the container before CloudFront exists, use the loopback checks in
section 4 (a Session Manager shell needs no ingress rule). Every create call below carries `Project=epicentre` and is
followed by `note`, which appends the id to the teardown file of section 2a.

### 3a. Security group and instance

```bash
TEARDOWN=~/.epicentre/teardown.env; . "$TEARDOWN"          # a fresh shell: brings REGION and the earlier ids back
note() { printf '%s=%s\n' "$1" "$2" >> "$TEARDOWN"; }       # the same helper as in section 2a (ids only)
VPC_ID=$(aws ec2 describe-vpcs --region $REGION --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNET_ID=$(aws ec2 describe-subnets --region $REGION \
  --filters Name=vpc-id,Values=$VPC_ID Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)
PL_ID=$(aws ec2 describe-managed-prefix-lists --region $REGION \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' --output text)
SG_ID=$(aws ec2 create-security-group --region $REGION --group-name epicentre-origin \
  --description "EPICENTRE origin: CloudFront prefix list only" --vpc-id $VPC_ID \
  --tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=epicentre-origin},{Key=Project,Value=epicentre}]' \
  --query GroupId --output text) && note SG_ID $SG_ID && note PL_ID $PL_ID
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID \
  --ip-permissions "IpProtocol=tcp,FromPort=8000,ToPort=8000,PrefixListIds=[{PrefixListId=${PL_ID},Description=CloudFront}]" \
  --tag-specifications 'ResourceType=security-group-rule,Tags=[{Key=Project,Value=epicentre}]'
```

No default VPC in the event account: use any subnet that routes to an internet gateway. The prefix list counts as all
of its entries against the default 60-rule quota of a group (AWS documents the weight as about 55, verify on the AWS console before use),
so this group carries no other ingress rule. For an AWS-managed list the API reports `MaxEntries` as `None`, so that
field proves nothing: the real proof is that the `authorize-security-group-ingress` call above succeeds (it did on the
live deploy, with 49 entries in the list that day). Inbound and outbound rules are counted separately.

**Outbound: TCP 443 only.** A new group allows all outbound traffic; this runbook replaces that with one rule. Everything
the instance has to reach is HTTPS (dnf, GitHub, Docker Hub, PyPI, Session Manager, Bedrock), and DNS, the instance
metadata service and time sync are not filtered by security groups, so port 443 is enough. The rule below is the only
`0.0.0.0/0` in the stack. It is outbound; nothing inbound is ever open to the world. The default rules are removed by
their ids (looked up, so whichever default rules this group has go, IPv4 and IPv6 alike), after the narrow rule exists.

```bash
aws ec2 authorize-security-group-egress --region $REGION --group-id $SG_ID \
  --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=HTTPS-out}]" \
  --tag-specifications 'ResourceType=security-group-rule,Tags=[{Key=Project,Value=epicentre}]'
aws ec2 describe-security-group-rules --region $REGION --filters Name=group-id,Values=$SG_ID \
  --query 'SecurityGroupRules[?IsEgress==`true` && IpProtocol==`"-1"`].SecurityGroupRuleId' --output text \
  | tr '\t' '\n' | xargs aws ec2 revoke-security-group-egress --region $REGION --group-id $SG_ID --security-group-rule-ids
aws ec2 describe-security-groups --region $REGION --group-ids $SG_ID \
  --query 'SecurityGroups[0].[IpPermissions[].[IpProtocol,FromPort,ToPort],IpPermissionsEgress[].[IpProtocol,FromPort,ToPort]]'
# expect exactly: inbound [tcp, 8000, 8000], outbound [tcp, 443, 443]
```

```bash
AMI_ID=$(aws ssm get-parameter --region $REGION \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
INSTANCE_ID=$(aws ec2 run-instances --region $REGION --image-id $AMI_ID --instance-type t3.small \
  --iam-instance-profile Name=epicentre-runtime --security-group-ids $SG_ID --subnet-id $SUBNET_ID \
  --associate-public-ip-address \
  --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --tag-specifications \
    'ResourceType=instance,Tags=[{Key=Name,Value=epicentre},{Key=Project,Value=epicentre},{Key=project,Value=poly-datathon-2026}]' \
    'ResourceType=volume,Tags=[{Key=Project,Value=epicentre}]' \
    'ResourceType=network-interface,Tags=[{Key=Project,Value=epicentre}]' \
  --query 'Instances[0].InstanceId' --output text) && note INSTANCE_ID $INSTANCE_ID
aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
ORIGIN_DNS=$(aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
aws ssm describe-instance-information --region $REGION \
  --filters Key=InstanceIds,Values=$INSTANCE_ID --query 'InstanceInformationList[0].PingStatus'   # "Online" in 1-2 min
```

Why these flags: no `--key-name` (Session Manager only); `HttpTokens=required` is IMDSv2; the hop limit is 2 because a
container sits one network hop behind the host, and with 1 it could not see the instance role. The public address is
there only so CloudFront can reach the origin; the group lets nothing else in. If `ORIGIN_DNS` is empty, turn on DNS
hostnames for the VPC. The tags: the instance carries `Name`, `Project=epicentre` and the lowercase
`project=poly-datathon-2026` (tag keys are case sensitive, so these are two different keys); its volume and its network
interface carry `Project=epicentre` too, so nothing the instance created is left untagged. Evidence for the pack:
`aws ec2 describe-security-groups --region $REGION --group-ids $SG_ID` shows one inbound rule (the prefix list) and one
outbound rule (TCP 443); the only `0.0.0.0/0` in it is that outbound rule, and none is inbound.

### 3b. CloudFront (HTTPS in front, Authorization forwarded, secret header added)

The distribution can exist before the app runs (it answers 502 until section 4 is done).

**The two secrets, generated once and never printed.** The password (gate 3) and the origin secret (gate 2) are random,
different from each other, and made on this laptop into **one owner-only file**, `~/.epicentre/secrets.env`, in the
`NAME=value` form that `docker run --env-file` reads. Nothing is printed: `printf` is a shell builtin, so a value never
appears in any process's argument list, and the file is written under `umask 077` (mode 600, in a mode-700 folder
outside the repo). The password is 24 URL-safe characters, the origin secret 48 hex characters (hex needs no quoting
anywhere). The `[ -e ... ] ||` guard keeps an existing file: generating again would leave the running app and
CloudFront with different values. The file is the one copy you keep; section 4 moves it to the instance, and section 7
deletes it.

```bash
umask 077
[ -e ~/.epicentre/secrets.env ] || { printf 'EPICENTRE_PASSWORD=%s\n' "$(openssl rand -base64 18 | tr '/+' '_-')"
  printf 'EPICENTRE_ORIGIN_SECRET=%s\n' "$(openssl rand -hex 24)"; } > ~/.epicentre/secrets.env
chmod 600 ~/.epicentre/secrets.env
ls -l ~/.epicentre/secrets.env | awk '{print $1, $5}'     # -rw------- and a size: the check that prints no value
```

Rules for these two values, everywhere in this runbook: never `echo` or `cat` the file, never put a value on a command
line, in a tag, in user-data, in an SSM parameter or in an SSM command, in the repo, in the README or in the video.
Read a value only through a pipe into the program that needs it (`sed ... | curl -K -`, below). To give the password to
the jury, copy it without printing it (`sed -n 's/^EPICENTRE_PASSWORD=\(.*\)$/\1/p' ~/.epicentre/secrets.env | pbcopy`
on macOS), paste it into the message, then clear the clipboard (`pbcopy < /dev/null`). Hex and URL-safe base64 contain
no quote, backslash or space, so the values need no escaping in the JSON and curl lines below; keep it so (no password
manager string with symbols in this file).

**The origin secret (gate 2).** CloudFront adds the header `X-Origin-Verify` with the origin secret to every request it
sends to the instance, and the app (section 4) answers 403 to anything without it. The block below reads the value from
the file into a shell variable (it stays in this shell's memory: not exported, not on any command line), writes it into
one owner-only JSON file, and the file is deleted the moment the distribution exists. The JSON has the
`Project=epicentre` tag for `create-distribution-with-tags`. The block also holds the two managed policy ids, which
were written from memory and not looked up: the hard gate after the block checks their names before anything is
created.

```bash
ORIGIN_SECRET=$(sed -n 's/^EPICENTRE_ORIGIN_SECRET=\(.*\)$/\1/p' ~/.epicentre/secrets.env)   # a shell variable, not exported
CACHE_POLICY_ID=4135ea2d-6df8-44a3-9df3-4b5a84be39ad     # Managed-CachingDisabled; verify on the AWS console before use
ORIGIN_POLICY_ID=216adef6-5c7f-47e4-b989-5492eafa07d3    # Managed-AllViewer; verify on the AWS console before use
CF_JSON=~/.epicentre/cf.json
touch "$CF_JSON" && chmod 600 "$CF_JSON"       # it will hold the origin secret: owner only
cat > "$CF_JSON" <<JSON
{"Tags": {"Items": [{"Key": "Project", "Value": "epicentre"}]},
 "DistributionConfig": {
  "CallerReference": "epicentre-$(date +%s)",
  "Comment": "EPICENTRE live app (three gates)",
  "Enabled": true,
  "PriceClass": "PriceClass_100",
  "HttpVersion": "http2",
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "epicentre-ec2", "DomainName": "$ORIGIN_DNS",
    "CustomHeaders": {"Quantity": 1, "Items": [{"HeaderName": "X-Origin-Verify",
                                                "HeaderValue": "$ORIGIN_SECRET"}]},
    "CustomOriginConfig": {"HTTPPort": 8000, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
                           "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 5}}]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "epicentre-ec2",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {"Quantity": 7, "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],
                       "CachedMethods": {"Quantity": 2, "Items": ["GET","HEAD"]}},
    "Compress": false,
    "CachePolicyId": "$CACHE_POLICY_ID",
    "OriginRequestPolicyId": "$ORIGIN_POLICY_ID"
  }
}}
JSON
```

**Hard gate before the distribution is created.** The two policy ids above were typed from memory. A wrong id fails
loudly, but a valid id of a different policy could let an edge cache pages from behind the password or drop the
`Authorization` header. So the two lookups below print the policy names, and the create call sits behind `&&`: it runs
only if they read exactly `Managed-CachingDisabled / Managed-AllViewer`. If the gate fails, nothing is created: correct
the two id lines from the console (CloudFront, Policies), run the first block again (it rewrites the file, which this
block deletes either way), then this one. `create-distribution-with-tags` is used instead of a plain create so that the
distribution is tagged `Project=epicentre` from its first second. The `list-tags-for-resource` line at the end proves
it; it needs `${ACCOUNT_ID}` from section 2b (with braces, for zsh), so set it again after a lost shell.

```bash
CACHE_NAME=$(aws cloudfront get-cache-policy --id $CACHE_POLICY_ID \
  --query CachePolicy.CachePolicyConfig.Name --output text)
ORIGIN_NAME=$(aws cloudfront get-origin-request-policy --id $ORIGIN_POLICY_ID \
  --query OriginRequestPolicy.OriginRequestPolicyConfig.Name --output text)
echo "$CACHE_NAME / $ORIGIN_NAME"          # must read exactly: Managed-CachingDisabled / Managed-AllViewer
unset DIST_ID                              # so a stale id from an earlier run cannot pass the check below
[ "$CACHE_NAME / $ORIGIN_NAME" = "Managed-CachingDisabled / Managed-AllViewer" ] \
  && DIST_ID=$(aws cloudfront create-distribution-with-tags --distribution-config-with-tags file://$HOME/.epicentre/cf.json \
       --query Distribution.Id --output text) \
  || echo "GATE FAILED: no distribution was created (a policy name differs, or the create call failed). Fix the ids, then run both blocks again."
rm -f "$CF_JSON"; unset ORIGIN_SECRET      # the file and the variable held the origin secret
: "${DIST_ID:?no distribution: do not go on}" && note DIST_ID $DIST_ID
aws cloudfront wait distribution-deployed --id $DIST_ID          # a few minutes
CF_DOMAIN=$(aws cloudfront get-distribution --id $DIST_ID --query Distribution.DomainName --output text)
echo "https://$CF_DOMAIN"
aws cloudfront list-tags-for-resource --resource arn:aws:cloudfront::${ACCOUNT_ID}:distribution/${DIST_ID} \
  --query 'Tags.Items[].[Key,Value]' --output text          # expect: Project  epicentre
```

- `4135ea2d-...` is AWS's managed cache policy `Managed-CachingDisabled`: nothing is stored at an edge, so no run and
  no page behind the password is ever cached. `216adef6-...` is the managed origin request policy `Managed-AllViewer`:
  it forwards the viewer's headers (so `Authorization`), cookies and query string to the origin. Both ids are
  unverified until a human has run the gate above (verify on the AWS console before use); to look names up yourself:
  `aws cloudfront list-cache-policies --type managed` and `list-origin-request-policies --type managed`.
- **Two commands print the origin secret: `aws cloudfront get-distribution-config` (the header value sits in the
  distribution config) and `docker inspect` on the instance (it lists the container's environment, the password
  included).** Never run either without a `--query` or `--format` that cuts the value out, never paste or save their
  output, and never save them as evidence (section 10 saves a filtered view with the header name only). The teardown
  replaces the CloudFront copy with a random value before the distribution is deleted (section 7), and every
  `update-distribution` there carries a `--query` so the rotated value is not printed either.
- **Our distribution is found by its comment, never by position.** This account holds at least one other CloudFront
  distribution that is not ours (its comment is empty). Ours has the comment `EPICENTRE live app ...` and the tag
  `Project=epicentre`, and its id is in the teardown file. When a lookup is needed:
  `aws cloudfront list-distributions --query "DistributionList.Items[?starts_with(Comment,'EPICENTRE')].Id" --output text`.
  Never update, disable or delete a distribution whose id is not in the teardown file.
- `Compress` is false so the NDJSON stream of a run is not held back for compression. `OriginReadTimeout` 60 is the
  default ceiling; the longest silent step of a run (the model call) is far shorter. `PriceClass_100` uses the
  cheapest edge locations (North America and Europe).
- The proof that the secret header and `Authorization` really reach the app is the smoke test at the end of section 4:
  no password gives 401 (a 403 there means CloudFront is not sending the right `X-Origin-Verify`), the right password
  gives 200. A password header stripped on the way would keep returning 401.

## 4. Install and run

Everything on the instance happens in a Session Manager shell (needs the `session-manager-plugin` on your laptop). The
shell is root on purpose: `sudo` resets the environment, which would silently start the container without its password.

```bash
aws ssm start-session --region us-east-1 --target <INSTANCE_ID>      # laptop: opens a shell on the instance
sudo -i                                                              # instance: root shell for the rest of section 4
dnf install -y docker git nmap-ncat && systemctl enable --now docker # Docker from the distro repo
```

**The code.** Repo public (it is again before Sun 22:00): `git clone https://github.com/<ORG>/<REPO>.git /opt/epicentre`.
Repo still private (the Sun 10:00 dry run): send `git archive` through the same pipe as the data, as the first send in
the block below, and it unpacks into `/opt/epicentre`. Never put a GitHub token on the instance.

**The licensed data** (`data/starter/`, `data/etf_holdings.csv`) is never in git and never in the image. Send it over the
Session Manager port-forward: no S3, no SSH key, and the security group admits nothing on port 9000.

```bash
# instance (root shell): wait for one tar stream; run this line again before every send (it stops after one transfer)
mkdir -p /opt/epicentre && cd /opt/epicentre && nc -l 9000 | tar xz

# laptop, second terminal: open the forward and leave it running
aws ssm start-session --region us-east-1 --target <INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["9000"],"localPortNumber":["9000"]}'

# laptop, third terminal, repo root (macOS nc: -N closes the connection at the end of the input)
git archive --format=tar.gz HEAD | nc -N 127.0.0.1 9000                      # send 1, private repo only: the code
tar cz data/starter data/etf_holdings.csv | nc -N 127.0.0.1 9000             # send 2: the licensed data
```

Back on the instance: `chmod -R a+rX /opt/epicentre/data` (the container user is uid 10001) and check
`ls -l /opt/epicentre/data/starter/prices_daily.csv /opt/epicentre/data/etf_holdings.csv`. Without the holdings file the
app falls back to direct holdings and says so (`mode: "direct"`, pitfall 10); without the starter prices `/api/health`
reports `"data": false`.

**The two secrets.** Both are in `~/.epicentre/secrets.env` on your laptop (section 3b): copy each one without printing
it (`sed -n 's/^EPICENTRE_PASSWORD=\(.*\)$/\1/p' ~/.epicentre/secrets.env | pbcopy`, then the same for
`EPICENTRE_ORIGIN_SECRET`), paste it at its `read -rs` prompt below, then clear the clipboard (`pbcopy < /dev/null`).
The password goes to the jury out of band; nobody else ever gets the origin secret. Neither is ever in
the repo, the README, the video, user-data or a tag. Type both into the root shell, where `read -rs` keeps them off the
screen and out of the shell history, and start the container with the variable *names* only. The two `:?` guards are
chained to `docker run` with `&&`, so an empty variable (a fresh shell, a restart script) stops the command instead of
starting a container without it:

```bash
printf 'EPICENTRE_PASSWORD: '; read -rs EPICENTRE_PASSWORD; echo; export EPICENTRE_PASSWORD
printf 'EPICENTRE_ORIGIN_SECRET: '; read -rs EPICENTRE_ORIGIN_SECRET; echo; export EPICENTRE_ORIGIN_SECRET
export EPICENTRE_GUARDRAIL_ID=<GUARDRAIL_ID> EPICENTRE_GUARDRAIL_VERSION=<GUARDRAIL_VERSION>
(umask 077; printf 'EPICENTRE_PASSWORD=%s\nEPICENTRE_ORIGIN_SECRET=%s\n' "$EPICENTRE_PASSWORD" "$EPICENTRE_ORIGIN_SECRET" \
  > /root/epicentre.env)                                         # root-only copy for the Redeploy block (printf is a builtin)
cd /opt/epicentre && docker build -t epicentre .
: "${EPICENTRE_PASSWORD:?type the password first}" \
  && : "${EPICENTRE_ORIGIN_SECRET:?type the origin secret first}" \
  && docker run -d --name epicentre --restart unless-stopped -p 8000:8000 \
  --log-opt max-size=10m --log-opt max-file=2 \
  -v "$PWD/data/starter:/app/data/starter:ro" -v "$PWD/data/etf_holdings.csv:/app/data/etf_holdings.csv:ro" \
  -e EPICENTRE_REQUIRE_PASSWORD=1 -e EPICENTRE_PASSWORD -e EPICENTRE_ORIGIN_SECRET \
  -e EPICENTRE_GUARDRAIL_ID -e EPICENTRE_GUARDRAIL_VERSION epicentre
```

No credential variable is set: boto3 finds the instance role by itself (IMDSv2). Docker keeps the container's
environment in a root-only file on the encrypted volume, which section 7 destroys.

Three layers keep the app from running open. The `:?` guards stop `docker run` when a variable is empty (without them,
`-e NAME` passes nothing for an unset variable). `EPICENTRE_REQUIRE_PASSWORD=1` makes the app itself refuse to start
without a password: a container that keeps restarting means a start-up refusal, so read `docker logs epicentre`, then
`docker rm -f epicentre` and run the block again. The origin secret has no such flag: when `EPICENTRE_ORIGIN_SECRET`
is unset the app does not check the header at all, so **do not go on until the two status codes below read 403 and
401.** The 403 line is the direct-to-instance smoke test: no CloudFront, no header, and the app must refuse.

```bash
curl -s http://127.0.0.1:8000/api/health                              # {"data":true,"bedrock":true,"guardrail":true}: open on purpose
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/       # 403: gate 2, straight to the instance without X-Origin-Verify
curl -s -o /dev/null -w '%{http_code}\n' -K - http://127.0.0.1:8000/ <<<"header = \"X-Origin-Verify: $EPICENTRE_ORIGIN_SECRET\""   # 401: right header, password asked
docker ps --format '{{.Names}} {{.Status}}'                           # "(healthy)" after about 30 seconds
```

The third command reads its header from standard input (`-K -`), so the secret never shows in the process list.

These checks use the instance's own loopback, which needs no ingress rule. A Session Manager forward of port 8000
(`aws ssm start-session ... --parameters '{"portNumber":["8000"],"localPortNumber":["8000"]}'`) also reaches the app from
your laptop, but only curl can send the secret header there: a browser on `127.0.0.1:8000` would see the 403. The browser
test is the one through CloudFront below.

**Smoke test through CloudFront** (laptop). Type the password with `read -rs` first. It goes to curl on standard input
(`-K -`), not with `-u`, so it never shows in the process list. A 403 on the first line means CloudFront is not sending
the right `X-Origin-Verify` (fix section 3b before anything else); a 401 on the second line means `Authorization` was
stripped on the way.

```bash
printf 'EPICENTRE_PASSWORD: '; read -rs EPICENTRE_PASSWORD; echo      # laptop shell; not exported
curl -s -o /dev/null -w '%{http_code}\n' "https://$CF_DOMAIN/"                                                  # 401: CloudFront added the header, the app asks for the password
curl -s -o /dev/null -w '%{http_code}\n' -K - "https://$CF_DOMAIN/" <<<"user = \"team:$EPICENTRE_PASSWORD\""    # 200: Authorization arrived
curl -s "https://$CF_DOMAIN/api/health"                                                                         # three booleans, no password
curl -s -m 5 -o /dev/null -w '%{http_code}\n' "http://$ORIGIN_DNS:8000/"                                        # 000: times out, the group admits CloudFront only (gate 1)
```

Then run one full live check from a browser on `https://$CF_DOMAIN/` and confirm it streams to the end (a stall of more
than 60 seconds between two chunks would end it with a 504). That run is also the "final trace" of section 10.

**Redeploy** (new commits on main, or the numbered guardrail version after the freeze: change `<GUARDRAIL_VERSION>`).
In a fresh root shell on the instance (`aws ssm start-session ...`, then `sudo -i`). The two secrets come from
`/root/epicentre.env`, written at the first start above, never from the screen: the `awk` guard stops `docker run` unless
the file holds two non-empty values, and `--env-file` passes them by name.

```bash
cd /opt/epicentre && git pull --ff-only && git log --oneline -1          # the commit the app will run
docker build -t epicentre . && docker rm -f epicentre
export EPICENTRE_GUARDRAIL_ID=<GUARDRAIL_ID> EPICENTRE_GUARDRAIL_VERSION=<GUARDRAIL_VERSION>
awk -F= 'length($2) { n++ } END { exit n != 2 }' /root/epicentre.env \
  && docker run -d --name epicentre --restart unless-stopped -p 8000:8000 \
  --log-opt max-size=10m --log-opt max-file=2 \
  -v "$PWD/data/starter:/app/data/starter:ro" -v "$PWD/data/etf_holdings.csv:/app/data/etf_holdings.csv:ro" \
  --env-file /root/epicentre.env -e EPICENTRE_REQUIRE_PASSWORD=1 -e EPICENTRE_COMMIT="$(git rev-parse HEAD)" \
  -e EPICENTRE_GUARDRAIL_ID -e EPICENTRE_GUARDRAIL_VERSION epicentre
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/       # 403: no X-Origin-Verify
sed -n 's/^EPICENTRE_ORIGIN_SECRET=\(.*\)$/header = "X-Origin-Verify: \1"/p' /root/epicentre.env \
  | curl -s -o /dev/null -w '%{http_code}\n' -K - http://127.0.0.1:8000/        # 401: right header, password asked
```

`EPICENTRE_COMMIT` names the commit in a container that has no `.git` (the image leaves it out). Then run the smoke test
through CloudFront above.

## 5. Show least privilege on video

From a Session Manager shell on the instance (the host's AWS CLI signs with the instance role):

```bash
aws sts get-caller-identity                                  # ...:assumed-role/epicentre-runtime/<INSTANCE_ID>
aws bedrock list-foundation-models --region us-east-1        # AccessDeniedException
```

The second call is denied because the runtime policy allows only `bedrock:InvokeModel` and `bedrock:ApplyGuardrail`, on
named resources. Then switch to the browser: a live run through `https://$CF_DOMAIN/` still works, so the app runs on
exactly the permissions it needs and nothing more. The policy simulator output (section 10) backs the clip with text.

## 6. Model invocation logging stays off

Inputs are never stored (spec section 6, red gate 6), so Bedrock model invocation logging is not enabled; it would write
prompts and answers to S3 or CloudWatch Logs. Check it from an admin shell and keep the output for the evidence pack:

```bash
aws bedrock get-model-invocation-logging-configuration --region us-east-1      # {} : no logging configured
```

There is no CloudWatch agent or log group on the instance. The container logs start-up lines only (`--no-access-log`, and
the app never logs an input or a credential), capped at 2 files of 10 MB. The CloudWatch graphs in the video are the
`AWS/Bedrock` and Guardrails metrics: counts and latencies, never content.

## 7. Tear down

Since Sun 15 Nov the stack also holds the record vault, its role statement and the dashboard: delete those first, in the
order of section 11, then run this section.

Do it Mon Nov 16 after 13:59 and after the evidence pack (section 10) is complete, or at once on any sign of abuse.
Kill switch, closes the origin in seconds (the distribution then answers 502):

```bash
aws ec2 revoke-security-group-ingress --region $REGION --group-id $SG_ID \
  --ip-permissions "IpProtocol=tcp,FromPort=8000,ToPort=8000,PrefixListIds=[{PrefixListId=$PL_ID}]"
```

Full teardown, in this order (a distribution must be disabled and deployed before it can be deleted; a security group
can only go once its instance is gone). If the shell variables are lost, look them up with
`aws ec2 describe-instances --region $REGION --filters Name=tag:Name,Values=epicentre Name=instance-state-name,Values=pending,running,stopped --query 'Reservations[].Instances[].InstanceId'`,
`aws ec2 describe-security-groups --region $REGION --filters Name=group-name,Values=epicentre-origin` and
`aws cloudfront list-distributions --query 'DistributionList.Items[].[Id,Comment]'`.

```bash
# disable the distribution and rotate the origin secret in the same update: the new value is random and nobody knows it
ETAG=$(aws cloudfront get-distribution-config --id $DIST_ID --query ETag --output text)
aws cloudfront get-distribution-config --id $DIST_ID --query DistributionConfig --output json \
  | python3 -I -c 'import json,secrets,sys; c=json.load(sys.stdin); c["Enabled"]=False; c["Origins"]["Items"][0]["CustomHeaders"]["Items"][0]["HeaderValue"]=secrets.token_hex(24); print(json.dumps(c))' > /tmp/epicentre-cf-off.json
aws cloudfront update-distribution --id $DIST_ID --if-match "$ETAG" --distribution-config file:///tmp/epicentre-cf-off.json
aws cloudfront wait distribution-deployed --id $DIST_ID
ETAG=$(aws cloudfront get-distribution-config --id $DIST_ID --query ETag --output text)
aws cloudfront delete-distribution --id $DIST_ID --if-match "$ETAG"

aws ec2 terminate-instances --region $REGION --instance-ids $INSTANCE_ID     # the volume and the container go with it
aws ec2 wait instance-terminated --region $REGION --instance-ids $INSTANCE_ID
aws ec2 delete-security-group --region $REGION --group-id $SG_ID

aws iam remove-role-from-instance-profile --instance-profile-name epicentre-runtime --role-name epicentre-runtime
aws iam delete-instance-profile --instance-profile-name epicentre-runtime
aws iam detach-role-policy --role-name epicentre-runtime --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name epicentre-runtime --policy-name epicentre-runtime
aws iam delete-role --role-name epicentre-runtime
rm -f /tmp/epicentre-cf.json /tmp/epicentre-cf-off.json /tmp/runtime-policy.filled.json /tmp/ec2-trust.json
unset EPICENTRE_ORIGIN_SECRET EPICENTRE_PASSWORD      # laptop: forget both; repeat in every shell where you typed them
```

**Rotating the secret.** The origin secret and the password are throwaways for this window. The disable step above
already replaced the value CloudFront held with a random one that nobody knows, terminating the instance destroys the
copy in the container's environment, and the last two lines remove the laptop's copies. Never reuse either value: a new
deployment starts with a new secret and a new password. If you suspect a leak during the live window, do not wait for
the teardown: run the kill switch at the top of this section, then relaunch with new values.

Check that nothing is left: re-run the three lookups above, each must come back empty. Then say in the technical doc that the live app ran Sun 23:00 to Mon 13:59 and is gone; the GitHub Pages demo remains.

## 8. Production path (documented, not built)

The same stateless container, run for real users: ECS Fargate in private subnets behind a load balancer with Cognito
login and our own domain (a TLS certificate from ACM, so TLS runs end to end and the two limits at the top disappear),
CloudFront and WAF rate limits in front, a task role equal to `docs/iam/runtime-policy.json`, an in-region inference
profile reached through a PrivateLink endpoint to `bedrock-runtime`, model invocation logging off, no input stored. Never a
public endpoint that spends our tokens. A broker would embed it as an education-centre module. No resource for this
section exists or is created.

## 9. Cost estimate

List prices as known to the author on 2026-11-14 (us-east-1, Linux, on-demand, USD). They were not re-fetched when this
was written, so every figure here is a **price to be checked against the dated AWS price pages** (EC2, EBS, public IPv4,
CloudFront) before launch: verify on the AWS console before use, and write down the date you read them.

| Item | Basis | Price (verify on the AWS console before use) | Amount | Estimate |
|---|---|---|---|---|
| EC2 t3.small | on-demand | 0.0208 per hour | up to 39 h | 0.81 |
| Public IPv4 address | per hour in use | 0.005 per hour | up to 39 h | 0.20 |
| EBS gp3, 20 GB | per GB-month | 0.08 | 39 h of a 730-hour month | 0.09 |
| CloudFront, `PriceClass_100` | always-free tier (1 TB out, 10 M requests a month), to be checked against the dated AWS price pages | 0 within the free tier | a few MB per run | 0.00 |
| Session Manager, EC2 to CloudFront transfer | no charge | 0 | n/a | 0.00 |
| **Infrastructure total** | | | | **about 1.10** |

The headline, quoted the same way in section 1: about 1.10 USD of infrastructure for the whole window, to be checked
against the dated AWS price pages.

**How the hours and the total are counted.** The window is Sat Nov 14 23:55 (the live deploy started) to Mon Nov 16
13:59 (the accounts close): 24 h from Sat 23:55 to Sun 23:55, plus 14 h 4 min to Mon 13:59, is 38 h 4 min, rounded up
to **39 billed hours** because the public IPv4 address is billed per started hour. Then 39 x 0.0208 = 0.81 for the
instance, 39 x 0.005 = 0.20 for the address (0.195, rounded up), and 20 GB x 0.08 x 39 / 730 = 0.09 for the volume
(0.0855, rounded up): 0.81 + 0.20 + 0.09 = **1.10**. The teardown runs before 13:59, so this is a ceiling. The
earlier estimate (28 hours from a Sun 23:00 start, 0.80 in total) assumed a later start and is gone. The prices are the ones
in the table, not re-fetched: read the current numbers on the dated AWS price pages (EC2, EBS, public IPv4,
CloudFront) and redo the three products if they differ.

The only cost that grows with visitors is Bedrock: every run shows its own cost
in the app (list prices in `config.PRICE_USD_PER_MTOK`, Sonnet 5.5 at 2.00 input and 10.00 output USD per million
tokens), so budget the runs you expect times that figure; the password is what bounds the number of runs. Before launch,
set an AWS Budgets alert on the account if the event role allows it.

## 10. Before Mon 13:59: the AWS evidence pack

The pack as captured on Sun 15 Nov, masked, is in `docs/aws_evidence/` and is indexed in [aws.md](aws.md) (the evidence
table); the list below is the original plan.

Capture the pack on the dry run, by **Sun 13:00** (other teams already have theirs), then re-capture items 1 and 6 on
Mon morning so they show the live window, and only then tear down (section 7). Save everything in
`~/epicentre-evidence/`, outside the repo. Before any file leaves your laptop, remove account IDs and check that no key
or token is in it: `grep -rEl 'AKIA|ASIA|SessionToken|aws_secret' ~/epicentre-evidence` must print nothing. Neither of
the two secrets may be in it either; run this while the variables are still set (before the teardown unsets them), and
it must print nothing (the values travel through a pipe, never on the command line):
`grep -rlF -f <(printf '%s\n%s\n' "$EPICENTRE_ORIGIN_SECRET" "$EPICENTRE_PASSWORD") ~/epicentre-evidence`
Both variables must be set in that shell: an empty one makes grep list every file. Run at least five live checks first, so the graphs have data. Run these from an admin shell unless it says "instance".

- [ ] **1. CloudWatch graph.** `aws cloudwatch list-metrics --region us-east-1 --namespace AWS/Bedrock` lists what exists
  (Guardrails metrics live in their own namespace). Screenshot a console graph of InvocationCount, InvocationLatency and
  token counts for `us.anthropic.claude-sonnet-5-5` over the last hour; the time range must be visible. File `01-cloudwatch.png`.
- [ ] **2. Guardrail JSON.** `aws bedrock get-guardrail --region us-east-1 --guardrail-identifier $GUARDRAIL_ID --guardrail-version $GUARDRAIL_VERSION > 02-guardrail.json`.
  The version must be a number, not `DRAFT`.
- [ ] **3. IAM policy and simulator output.** The policy the role really carries, then what it allows and denies:

```bash
aws iam get-role-policy --role-name epicentre-runtime --policy-name epicentre-runtime > 03-iam-policy.json
ROLE_ARN=arn:aws:iam::$ACCOUNT_ID:role/epicentre-runtime
Q='EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision]'
aws iam simulate-principal-policy --policy-source-arn $ROLE_ARN --action-names bedrock:InvokeModel \
  --resource-arns arn:aws:bedrock:us-east-1:$ACCOUNT_ID:inference-profile/us.anthropic.claude-sonnet-5-5 --query "$Q" --output text > 04-simulator.txt
aws iam simulate-principal-policy --policy-source-arn $ROLE_ARN --action-names bedrock:ApplyGuardrail \
  --resource-arns arn:aws:bedrock:us-east-1:$ACCOUNT_ID:guardrail/$GUARDRAIL_ID --query "$Q" --output text >> 04-simulator.txt
aws iam simulate-principal-policy --policy-source-arn $ROLE_ARN \
  --action-names bedrock:ListFoundationModels bedrock:CreateGuardrail s3:ListAllMyBuckets iam:CreateRole ec2:RunInstances \
  --query "$Q" --output text >> 04-simulator.txt
```

  Expected: two `allowed`, five `implicitDeny`. Also keep the denied `aws bedrock list-foundation-models` from the
  instance (section 5) as `04-denied-on-instance.txt`.
- [ ] **4. Model access.** Proof that the model is enabled and answers in this account: `python scripts/check_bedrock.py`
  and `aws bedrock list-foundation-models --region us-east-1 --by-provider anthropic --query "modelSummaries[?contains(modelId,'sonnet-5')].[modelId,modelLifecycle.status]" --output text`,
  both into `05-model-access.txt` (admin shell, not the instance: the instance is denied this call by design).
- [ ] **5. Network and hardening.** Three files that show the closed door, with no `0.0.0.0/0` in any of them:
  `aws ec2 describe-security-groups --region $REGION --group-ids $SG_ID > 06-security-group.json`;
  `aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID --query 'Reservations[].Instances[].[MetadataOptions,IamInstanceProfile.Arn,KeyName]' > 07-instance.json`
  (IMDSv2 `required`, an instance profile, no key name);
  `aws cloudfront get-distribution-config --id $DIST_ID --query 'DistributionConfig.{Enabled:Enabled,Origins:Origins.Items[].{DomainName:DomainName,Protocol:CustomOriginConfig.OriginProtocolPolicy,CustomHeaderNames:CustomHeaders.Items[].HeaderName},Behavior:DefaultCacheBehavior.{Viewer:ViewerProtocolPolicy,CachePolicyId:CachePolicyId,OriginRequestPolicyId:OriginRequestPolicyId}}' > 08-cloudfront.json`
  (`redirect-to-https`, the two managed policies, the header name `X-Origin-Verify`). The unfiltered config holds the
  origin secret itself: never save it as evidence.
- [ ] **6. A final trace.** One last live check through `https://$CF_DOMAIN/`, in a browser, address bar visible. Save the
  finished Result (its `trace` rows carry each Bedrock `RequestId`, token usage and latency) as `09-final-trace.json`,
  and the receipt screen as `09-final-trace.png`. Cross-check: that run's invocation shows in the CloudWatch graph of item 1.
- [ ] **7. Logging off.** The output of section 6 (`{}`) as `10-logging-off.json`.
- [ ] **8. Close the loop.** The files listed in the technical doc and README with no account ID or password visible;
  the teardown commands of section 7 run only after this box is ticked; the doc says the live app ran Sun 23:00 to Mon 13:59.

If the live app could not be launched (a no-go in section 1), items 1 to 4, 7 and the local part of 6 still apply: run
them against the local app with `EPICENTRE_GUARDRAIL_ID` set, and say in the doc that the app was local for the demo.

## 11. Sun 15 Nov: what the final deploy added (after the go of 09:10)

Every resource below carries `Project=epicentre` where it can, and is in the local teardown file. No id is written here.

- **The record vault (S3).** One bucket, `epicentre-records-<ID>` (a random suffix; found by that prefix and the tag): all
  four Block Public Access switches on, no bucket policy, ACLs off, versioning, SSE-S3, Object Lock enabled at creation with
  a default GOVERNANCE retention of 7 days, and a lifecycle rule that expires records after 30 days. Verified settings:
  [06-record-vault.json](aws_evidence/06-record-vault.json).
- **The role's one vault statement.** A second inline policy on `epicentre-runtime`, `epicentre-records`, is
  [`docs/iam/records-policy.json`](iam/records-policy.json) with the bucket name filled in at put time: `s3:PutObject`,
  `s3:PutObjectRetention`, `s3:GetObject` and `s3:GetObjectVersion` on `records/*` only, GOVERNANCE locks only. The policy
  simulator on the role: [04-simulator.txt](aws_evidence/04-simulator.txt).
- **The app.** `record_store.py` and `POST /api/record` (its body cap is 128 KB; every other route keeps 64 KB);
  `/api/health` also reports `holdings` and `deep`. The container runs with `EPICENTRE_GUARDRAIL_VERSION=1`,
  `EPICENTRE_RECORD_BUCKET` and `EPICENTRE_RECORD_LOCK_DAYS=7`.
- **The CloudWatch dashboard `epicentre`.** Built-in metrics only: Bedrock invocations, latency, tokens, throttles and
  errors for the model ids in `config.py`; Guardrails calls, interventions, latency and text units; the instance's CPU.
  Model invocation logging stays off (section 6). [05-dashboard.png](aws_evidence/05-dashboard.png).
- **Guardrail version 1.** Published with `CreateGuardrailVersion` from the evaluated DRAFT after a field-by-field check
  that the DRAFT equals `scripts/create_guardrail.py`'s configuration. `create_guardrail.py --publish` was not used: it
  updates the DRAFT before publishing. [02-guardrail.json](aws_evidence/02-guardrail.json).
- **The data on the instance.**
  - No agent copies the licensed local files. On the instance, the organizers' `build_dataset.py`, read line by line
    first, rebuilt `data/starter` in a throwaway container: no AWS credentials, and the metadata endpoint dropped by an
    iptables rule for that container network only, removed afterwards.
  - Holdings fetched there are dated after the replay's last day, so the app reads funds directly (the look-through
    rule, red gate 3), and the live page says so in one line.
  - A human sends the laptop's holdings file and deep panel with `/tmp/epi_deploy/send_data.sh`: SSM port-forward and
    `ncat` into `/root/epicentre-data/` (files 0600, owned by the container's uid, mounted read-only). It then restarts
    the container and checks `/api/health`.
  - Evidence: [11-live-data.md](aws_evidence/11-live-data.md).
- **The final redeploy (Sun 15 Nov, about 13:50 EST).**
  1. `git pull --ff-only`, and the previous image tagged `epicentre:prev`.
  2. A pre-flight: one `ApplyGuardrail` on version 1 with the instance role, before anything is switched.
  3. The container recreated with the env above and three read-only mounts (`data/starter`,
     `/root/epicentre-data/etf_holdings.csv`, `/root/epicentre-data/deep`). It rolls back to `epicentre:prev` by itself
     if `/api/health` does not answer within 60 s.
  4. Loopback 403 / 401 / 200.
  5. The smoke test through CloudFront with the password (never printed): the four investors live, the buy-or-sell
     question refused with no model call, one sealed record stored, the scenario routes. Evidence:
     [01-request-ids.txt](aws_evidence/01-request-ids.txt), [03-blocked-question.json](aws_evidence/03-blocked-question.json),
     [06-sealed-record.json](aws_evidence/06-sealed-record.json).

**Teardown additions, newest first, before section 7.** The local teardown file runs them in this order (its `--dry-run`
lists them):

```bash
aws cloudwatch delete-dashboards --dashboard-names epicentre
aws iam delete-role-policy --role-name epicentre-runtime --policy-name epicentre-records    # the app can no longer write
B=$(aws s3api list-buckets --query "Buckets[?starts_with(Name,'epicentre-records-')].Name | [0]" --output text)
aws s3api list-object-versions --bucket "$B" --output json \
  --query '{Objects: [Versions[].{Key: Key, VersionId: VersionId}, DeleteMarkers[].{Key: Key, VersionId: VersionId}][], Quiet: `true`}' \
  > /tmp/vault-delete.json
aws s3api delete-objects --bucket "$B" --bypass-governance-retention --delete file:///tmp/vault-delete.json   # GOVERNANCE, never COMPLIANCE
aws s3api delete-bucket --bucket "$B" && rm -f /tmp/vault-delete.json
```
