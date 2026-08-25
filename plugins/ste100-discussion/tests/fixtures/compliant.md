## How the shipping provider is wired up

`bin/dispatch-worker.ts:22-24` hardcodes three values. They are
`SHIPPO_ACCOUNT_ID`, `SHIPPO_API_KEY`, and `SHIPPO_ORIGIN_CODE`. The origin
code points at the vendor sandbox, `SG-TEST-01`.

CDK passes all three to Lambda as plain environment variables. See
`lib/dispatch-stack.ts` lines 61-63 and 88-90. The repo uses neither Secrets
Manager nor SSM Parameter Store. So the API key sits in plaintext in a
git-tracked file.

Two Lambdas talk to the provider:

- `callbackLambda` in `src/callback/callback.mjs` accepts inbound tracking
  updates. It checks the `X-Shippo-Signature` header. Then it invokes
  `dispatchLambda`.
- `dispatchLambda` in `src/dispatch/dispatch-handler.mjs` builds the label
  request. It posts that request to the vendor REST API.

Both Lambdas share one helper, `src/helpers/shippo.mjs`. The helper calls the
REST API through fetch with Basic Auth. The repo does not use the vendor SDK.
`package.json` does not list the SDK at all.

API Gateway exposes a public POST /callback route at
`lib/dispatch-stack.ts:118-124`. The provider calls that route. API Gateway
does not authenticate the caller. Instead the Lambda checks an HMAC signature.
A `CALLBACK_CANONICAL_URL` variable hardens that check against stage URL
mismatches.

One flag. The account id and API key at `bin/dispatch-worker.ts:22-23` look
like live credentials. Rotate them. Then move them into Secrets Manager.
