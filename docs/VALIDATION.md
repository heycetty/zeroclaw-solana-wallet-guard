# Validation record

Validated on 2026-08-05 UTC against ZeroClaw 0.8.4.

## Offline tests

```text
test_base58_address_validation ... ok
test_first_run_is_baseline ... ok
test_invalid_state_fails_closed ... ok
test_large_sol_delta_and_failed_signature_alert ... ok
test_private_rpc_is_fail_closed ... ok
test_prompt_injection_text_never_enters_report ... ok
test_rpc_method_allowlist ... ok
test_saturated_signature_window_marks_count_as_inexact ... ok
test_token_change_uses_mint_and_numbers_only ... ok
test_truncated_snapshots_do_not_claim_token_deltas ... ok

Ran 10 tests
OK
```

## ZeroClaw-native validation

The official CLI returned:

```text
Skill audit passed for ./skills/solana-wallet-guard (2 files scanned).
Installed skills (1):
[loaded by agent 'guard'] solana-wallet-guard v0.1.0
Tools: scan_wallet
```

A real agent turn invoked `solana-wallet-guard__scan_wallet` after an explicit
operator approval. A repeat read at 2026-08-05 08:39:04 UTC reported:

```text
status: no_change
balance: 9.297981773 SOL
token accounts: 395 returned, not truncated
token diff reliable: true
recent-signature window saturated: true; count marked inexact
custody tier: T0_READ_ONLY
transaction construction/signing/broadcast: false/false/false
```

## Live RPC boundary

The live test used an operator-supplied public wallet and the protected RPC
wrapper. No provider URL, key, private key, seed, or personally identifying
address mapping was copied into the repository or validation output. The public
address is visible only in the linked demo because the operator selected it for
that showcase.
