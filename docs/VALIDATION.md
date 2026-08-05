# Validation record

Validated on 2026-08-04 UTC against ZeroClaw 0.8.4.

## Offline tests

```text
test_base58_address_validation ... ok
test_first_run_is_baseline ... ok
test_large_sol_delta_and_failed_signature_alert ... ok
test_private_rpc_is_fail_closed ... ok
test_prompt_injection_text_never_enters_report ... ok
test_rpc_method_allowlist ... ok
test_token_change_uses_mint_and_numbers_only ... ok
test_truncated_snapshots_do_not_claim_token_deltas ... ok

Ran 8 tests
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
operator approval. Its final summary reported new signatures, zero SOL delta,
no token delta, custody tier `T0_READ_ONLY`, and confirmed that no transaction
was constructed, signed, or broadcast.

## Live RPC boundary

The live test used the operator's protected RPC wrapper. No provider URL or key
was copied into the repository or validation output. The configured public demo
address was the Compute Budget program address; replace it with a real public
wallet address before recording the final demo.
