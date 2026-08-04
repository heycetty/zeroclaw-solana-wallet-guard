# Three-minute demo outline

1. Show the project tree and the ZeroClaw skill inventory.
2. Open `THREAT_MODEL.md`: point out T0 custody and the three-method RPC
   allowlist.
3. Run the skill once against a public demo address. Explain the baseline
   result and bounded output.
4. Run it again to show deterministic `no_change` or new activity.
5. Show the prompt-injection test: a malicious memo string is present in a test
   fixture, but absent from the guard report because memos and logs are never
   fetched.
6. End with the operator workflow: cron invokes the skill, ZeroClaw summarizes
   only alerts, and a human investigates in an explorer. No wallet connection
   or signing occurs.

