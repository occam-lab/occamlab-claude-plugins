## How the shipping provider is wired up

Credentials are hardcoded in `bin/dispatch-worker.ts:22-24` — `SHIPPO_ACCOUNT_ID`,
`SHIPPO_API_KEY`, and `SHIPPO_ORIGIN_CODE` (the vendor's sandbox origin `SG-TEST-01`).
CDK passes these as plain Lambda environment variables in `lib/dispatch-stack.ts`
(lines 61-63 and 88-90). There is no Secrets Manager or SSM Parameter Store use — the
API key sits in plaintext in a git-tracked file, alongside the internal CMS key and the
analytics token.

Two Lambdas talk to the provider:

- `callbackLambda` (`src/callback/callback.mjs`) receives inbound tracking updates,
  validating the `X-Shippo-Signature` header before invoking `dispatchLambda`
  asynchronously.
- `dispatchLambda` (`src/dispatch/dispatch-handler.mjs`) is invoked by the callback and
  sends the label request back over the vendor's REST API.

Both use a shared helper, `src/helpers/shippo.mjs`, which calls the vendor's REST API
directly with fetch and Basic Auth (no official SDK — it's not even a package.json
dependency).

Inbound path: API Gateway exposes a public POST /callback route
(`lib/dispatch-stack.ts:118-124`) that the provider calls. It's intentionally
unauthenticated at the API Gateway layer — security instead comes from validating the
HMAC signature inside the Lambda, which is being hardened by a
`CALLBACK_CANONICAL_URL` env var against proxy and stage URL mismatches.

One flag: the account id and API key in `bin/dispatch-worker.ts:22-23` look like live
credentials committed in plaintext. Worth rotating and moving to Secrets Manager if this
hasn't already been addressed.
