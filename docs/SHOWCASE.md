# Discord showcase

## Solana Wallet Guard — T0 read-only monitoring for ZeroClaw

I built a bounded wallet-change detector for operators who want ZeroClaw to
watch a public treasury, service, fee, grant, or personal address without ever
giving an LLM custody of funds.

**Real run:** stock ZeroClaw 0.8.4 loaded the skill and invoked it after one
operator approval. The 64-second terminal demo shows a public address with
9.297981773 SOL and 395 legacy SPL token accounts. The repeated scan reports no
change, complete token inventory, T0 custody, and no transaction construction,
signing, or broadcast.

**What uses ZeroClaw:** a native `SKILL.toml`, one bounded `scan_wallet` tool,
operator approval, and an optional narrowly scoped cron prompt. ZeroClaw gets a
small deterministic JSON report rather than raw RPC responses.

**What I built:** a dependency-free Python scanner, a strict three-method RPC
allowlist, SSRF/private-network checks, atomic mode-0600 snapshots, SOL/SPL and
signature diffs, truncation handling, and 10 offline tests plus GitHub Actions.

**Custody and threat model:** T0 Read. There are no keys and no transaction
code. The scanner never requests transactions, memos, logs, token names, or
arbitrary account text, so those injection surfaces do not enter the model. It
fails closed on invalid snapshot state, suppresses token deltas when inventory
is truncated, and marks saturated signature windows as inexact. Remaining
limits: polling cannot prevent transfers, a compromised RPC can lie, and the
current token inventory excludes Token-2022.

Demo: https://x.com/clknoiz06/status/2084919175919583339

GitHub: https://github.com/heycetty/zeroclaw-solana-wallet-guard

Validation: https://github.com/heycetty/zeroclaw-solana-wallet-guard/blob/main/docs/VALIDATION.md
