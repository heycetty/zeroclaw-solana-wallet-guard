# Solana Wallet Guard for ZeroClaw

A small T0/read-only ZeroClaw skill that watches one Solana address and emits a
bounded, deterministic change report. The agent explains the report; it never
receives wallet keys and cannot construct, sign, simulate, or send a
transaction.

[![test](https://github.com/heycetty/zeroclaw-solana-wallet-guard/actions/workflows/test.yml/badge.svg)](https://github.com/heycetty/zeroclaw-solana-wallet-guard/actions/workflows/test.yml)

**Validated with stock ZeroClaw 0.8.4 · 10 offline tests · [64-second live
demo](https://x.com/clknoiz06/status/2084919175919583339)**

## Who should run it

This is for an operator who wants a daily change detector for a public treasury,
service, fee, grant, or personal wallet without turning an LLM agent into a hot
wallet. ZeroClaw can run it on demand or by cron, summarize the bounded report,
and route an alert to the operator's existing channel.

## What it detects

- SOL balance changes above an operator-defined threshold
- SPL token balance changes, represented by mint address and numeric delta
- new recent signatures and failed signatures
- token-account result truncation

When either comparison snapshot is truncated, the guard marks token deltas as
unreliable and suppresses them instead of presenting partial inventory changes
as real wallet activity.

The first scan establishes a baseline. Later scans compare current public-chain
state with the last local snapshot.

```text
ZeroClaw cron or operator prompt
              |
              v
 solana-wallet-guard__scan_wallet
              |
              v
 bounded read-only JSON-RPC  --->  trusted Solana RPC
              |
              v
 deterministic local snapshot diff
              |
              v
 small JSON report  --->  ZeroClaw operator summary
```

## Why this is a ZeroClaw use case

The repository includes a native `SKILL.toml` with a `scan_wallet` tool. A stock
ZeroClaw binary can load it, call the deterministic scanner, and turn the small
JSON result into an operator-friendly alert. The scanner deliberately keeps
untrusted on-chain text out of the model context.

## Quick start

Requirements: Python 3.10 or newer, ZeroClaw 0.8.4, and an operator-supplied
Solana RPC URL. The scanner itself uses only the Python standard library.

1. Copy the configuration and insert a public wallet address:

   ```sh
   cp config/guard.example.json config/guard.json
   ```

2. Supply `SOL_RPC` through your secret manager or secure command wrapper. Do
   not commit provider URLs containing API keys. If ZeroClaw's sanitized skill
   environment does not inherit `SOL_RPC`, set `env_wrapper` in the untracked
   `guard.json` to an absolute executable wrapper that injects it.

3. Run the deterministic scanner directly:

   ```sh
   python3 scripts/wallet_guard.py scan --config config/guard.json
   ```

4. Install and audit the skill from the project root:

   ```sh
   zeroclaw skills install ./skills/solana-wallet-guard --agent default
   zeroclaw skills audit ./skills/solana-wallet-guard
   zeroclaw skills list --agent default
   ```

5. Ask ZeroClaw: `Run the Solana wallet guard and explain only actionable changes.`

For unattended polling, create a narrowly scoped ZeroClaw cron job after the
wallet and alert destination are configured:

```sh
zeroclaw cron add '*/15 * * * *' \
  'Run the configured Solana wallet guard. Report only actionable changes.' \
  --agent guard --prompt \
  --allowed-tool solana-wallet-guard__scan_wallet \
  --uses-memory false
```

## Test

The test suite uses fixtures and makes no network requests:

```sh
python3 -m unittest discover -s tests -v
```

For a live read-only check, run the scanner through your configured Solana RPC
wrapper. No transaction is created or broadcast.

## Security

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). The RPC client has a strict
three-method allowlist, validates public keys, caps response sizes and list
lengths, rejects private network targets by default, and omits memos, logs,
token metadata, and arbitrary account contents.

Two fail-closed details matter in long-running monitoring:

- a corrupt or mismatched local snapshot stops the scan instead of silently
  replacing history with a new baseline;
- when the recent-signature window reaches its configured limit, the report
  marks the activity count as inexact instead of implying complete history.

## Current limits

- polling, not real-time prevention
- one configured address per deployment
- legacy SPL Token Program accounts only; Token-2022 accounts are not queried
- no token-price or token-legitimacy claims
- no alert channel bundled yet; ZeroClaw supplies the channel and schedule

## Evidence

- `python3 -m unittest discover -s tests -v`: 10 tests pass in CI and locally
- ZeroClaw `skills audit`: passed, 2 skill files scanned
- ZeroClaw 0.8.4 loaded the skill for agent `guard`
- On 2026-08-05, a real agent turn scanned an operator-supplied public address:
  `9.297981773 SOL`, 395 legacy SPL token accounts, complete token inventory,
  and `T0_READ_ONLY` with no construction, signing, or broadcast
- [Validation record](docs/VALIDATION.md) · [threat model](docs/THREAT_MODEL.md)
  · [paste-ready showcase](docs/SHOWCASE.md)

Questions and reproducible bug reports are welcome in [GitHub
Issues](https://github.com/heycetty/zeroclaw-solana-wallet-guard/issues).

## License

MIT
