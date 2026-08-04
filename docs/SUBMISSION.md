# Submission draft

## Title

Solana Wallet Guard — a T0, prompt-injection-resistant watcher for ZeroClaw

## One-line description

A stock ZeroClaw agent watches a Solana address, detects SOL/token/activity
changes, and produces bounded operator alerts without ever receiving keys or
building transactions.

## The problem

Wallet monitoring agents are often given too much power or too much untrusted
chain data. A simple alerting job should not need custody, signing rights, full
transaction payloads, arbitrary token metadata, or program logs in its model
context.

## The use case

An operator configures one public Solana address. ZeroClaw invokes the guard on
demand or by cron. The deterministic scanner performs three read-only RPC calls,
compares the result with a mode-0600 local snapshot, and returns a small JSON
report. ZeroClaw explains only the changes that deserve attention.

## What was built

- native ZeroClaw `SKILL.toml` and `scan_wallet` tool
- dependency-free Python scanner
- strict RPC method allowlist
- base58 public-key validation
- endpoint and private-network checks
- bounded signatures, token accounts, response bytes, and model output
- atomic private snapshot storage
- SOL, SPL-token, new-signature, and failed-signature change detection
- seven deterministic tests, including a malicious Memo fixture
- threat model, deployment guide, and three-minute demo outline

## Custody and safety

Custody tier: **T0 Read**.

The project cannot construct, simulate, sign, or broadcast transactions. It
does not accept seed phrases or private keys. It never requests `getTransaction`,
so memos, instructions, program logs, token names, and arbitrary chain text do
not reach the LLM. The prompt-injection test places a malicious instruction in a
mock RPC Memo field and proves that the resulting snapshot does not contain it.

## Reproduce

1. Clone the repository.
2. Copy `config/guard.example.json` to the ignored `config/guard.json`.
3. Set a public wallet address and provide `SOL_RPC` through a secret manager or
   secure wrapper.
4. Run the seven offline tests.
5. Install and audit the included skill with the stock ZeroClaw CLI.
6. Ask the `guard` agent to scan, then optionally attach a narrowly scoped cron
   job allowing only `solana-wallet-guard__scan_wallet`.

## Judging alignment

- **Use case:** useful daily monitoring with a clear operator action.
- **Safety:** T0 custody, fail-closed methods and endpoints, no untrusted text.
- **Craft:** deterministic core, atomic state, bounded output, seven tests.
- **Reproducibility:** standard library only and a stock ZeroClaw skill.
- **Showcase:** baseline, activity alert, and injection-defense proof fit in
  under three minutes.

## Links to add before submission

- GitHub repository: `[TODO]`
- Demo video: `[TODO]`
- ZeroClaw Discord showcase: `[TODO]`
- Build-in-public post: `[TODO]`

