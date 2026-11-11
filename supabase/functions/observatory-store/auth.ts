import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey, type CryptoKey } from "jose";

export const AUDIENCE = "https://jrndagmzayiwpmyjtczx.supabase.co/functions/v1/observatory-store";
export const ISSUER = "https://token.actions.githubusercontent.com";
const REPOSITORY = "chengyu-ucsb/ai-attention-observatory";
const WORKFLOWS = new Set([
  "prepare-weekly-readings.yml", "finalize-weekly-readings.yml", "database-check.yml",
].map((file) => `${REPOSITORY}/.github/workflows/${file}@refs/heads/main`));
const SUBJECTS = new Set([
  `repo:${REPOSITORY}:ref:refs/heads/main`,
  "repo:chengyu-ucsb@242127341/ai-attention-observatory@1424112251:ref:refs/heads/main",
]);
const KEYS = createRemoteJWKSet(new URL(`${ISSUER}/.well-known/jwks`), {
  timeoutDuration: 5000, cooldownDuration: 30000,
});

export async function verifyGithubToken(token: string, keys: JWTVerifyGetKey | CryptoKey = KEYS) {
  const { payload } = await jwtVerify(token, keys, {
    algorithms: ["RS256"], issuer: ISSUER, audience: AUDIENCE,
    requiredClaims: ["sub", "exp", "iat", "nbf", "jti"],
    maxTokenAge: "10m", clockTolerance: 5,
  });
  if (payload.repository !== REPOSITORY || payload.repository_id !== "1424112251" ||
      payload.repository_owner_id !== "242127341" || payload.ref !== "refs/heads/main" ||
      payload.ref_type !== "branch" || !SUBJECTS.has(String(payload.sub)) ||
      !WORKFLOWS.has(String(payload.workflow_ref)) ||
      !["push", "schedule", "workflow_dispatch", "workflow_run"].includes(String(payload.event_name)) ||
      !/^\d+$/.test(String(payload.run_id)) || !/^\d+$/.test(String(payload.run_attempt)) ||
      !/^[0-9a-f]{40}$/.test(String(payload.workflow_sha)) ||
      Number(payload.exp) - Number(payload.iat) > 600) {
    throw new Error("workflow_not_authorized");
  }
  return payload;
}
