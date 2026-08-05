#!/usr/bin/env python3
"""Bounded, deterministic, read-only Solana wallet monitor for ZeroClaw."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


ALLOWED_METHODS = frozenset(
    {"getBalance", "getSignaturesForAddress", "getTokenAccountsByOwner"}
)
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_INDEX = {character: index for index, character in enumerate(BASE58_ALPHABET)}
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class GuardError(RuntimeError):
    """An expected, safe-to-display guard failure."""


def decode_base58(value: str) -> bytes:
    number = 0
    try:
        for character in value:
            number = number * 58 + BASE58_INDEX[character]
    except KeyError as exc:
        raise GuardError("wallet_address is not valid base58") from exc

    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading_zeroes + decoded


def validate_wallet_address(value: Any) -> str:
    if not isinstance(value, str) or not 32 <= len(value) <= 44:
        raise GuardError("wallet_address must be a 32-byte Solana public key")
    if len(decode_base58(value)) != 32:
        raise GuardError("wallet_address must decode to exactly 32 bytes")
    return value


def parse_env_reference(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value:
        raise GuardError("rpc_url must be a non-empty string")
    if value.startswith("env:"):
        variable = value[4:]
        if not variable or not variable.replace("_", "A").isalnum():
            raise GuardError("rpc_url contains an invalid environment reference")
        return os.environ.get(variable), variable
    return value, None


def host_is_private(hostname: str) -> bool:
    normalized = hostname.strip("[]").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".local"):
        return True
    try:
        addresses = {ipaddress.ip_address(normalized)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError) as exc:
            raise GuardError("RPC hostname could not be resolved") from exc
    return any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        for address in addresses
    )


def validate_rpc_url(value: str, allow_private: bool) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise GuardError("rpc_url must be an HTTP(S) URL")
    if parsed.username or parsed.password:
        raise GuardError("rpc_url must not use URL userinfo credentials")
    if not allow_private and host_is_private(parsed.hostname):
        raise GuardError("private or local RPC targets are disabled")
    return value


def bounded_integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GuardError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise GuardError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class GuardConfig:
    wallet_address: str
    rpc_url: str
    state_path: pathlib.Path
    commitment: str
    max_signatures: int
    max_token_accounts: int
    sol_change_threshold_lamports: int
    allow_private_rpc: bool


def load_config(path: pathlib.Path) -> tuple[GuardConfig, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GuardError(f"config file not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardError("config file is not readable JSON") from exc

    if not isinstance(raw, dict):
        raise GuardError("config root must be an object")

    address = validate_wallet_address(raw.get("wallet_address"))
    rpc_url, missing_env = parse_env_reference(raw.get("rpc_url"))
    if missing_env and not rpc_url:
        raise GuardError(f"RPC environment variable is not set: {missing_env}")
    assert rpc_url is not None

    allow_private = raw.get("allow_private_rpc", False)
    if not isinstance(allow_private, bool):
        raise GuardError("allow_private_rpc must be true or false")
    rpc_url = validate_rpc_url(rpc_url, allow_private)

    commitment = raw.get("commitment", "confirmed")
    if commitment not in {"processed", "confirmed", "finalized"}:
        raise GuardError("commitment must be processed, confirmed, or finalized")

    max_signatures = bounded_integer(raw.get("max_signatures", 10), "max_signatures", 1, 25)
    max_token_accounts = bounded_integer(
        raw.get("max_token_accounts", 500), "max_token_accounts", 1, 500
    )
    try:
        sol_threshold = Decimal(str(raw.get("sol_change_threshold", "0.1")))
    except InvalidOperation as exc:
        raise GuardError("sol_change_threshold must be numeric") from exc
    if sol_threshold < 0 or sol_threshold > Decimal("1000000"):
        raise GuardError("sol_change_threshold is out of range")

    state_value = raw.get("state_path", "../.state/wallet-guard.json")
    if not isinstance(state_value, str) or not state_value:
        raise GuardError("state_path must be a non-empty string")
    state_path = pathlib.Path(state_value).expanduser()
    if not state_path.is_absolute():
        state_path = (path.parent / state_path).resolve()

    return (
        GuardConfig(
            wallet_address=address,
            rpc_url=rpc_url,
            state_path=state_path,
            commitment=commitment,
            max_signatures=max_signatures,
            max_token_accounts=max_token_accounts,
            sol_change_threshold_lamports=int(sol_threshold * Decimal(1_000_000_000)),
            allow_private_rpc=allow_private,
        ),
        raw,
    )


def maybe_run_through_wrapper(
    raw_config: dict[str, Any], config_path: pathlib.Path, argv: list[str]
) -> int | None:
    rpc_reference = raw_config.get("rpc_url")
    if not isinstance(rpc_reference, str) or not rpc_reference.startswith("env:"):
        return None
    variable = rpc_reference[4:]
    if os.environ.get(variable):
        return None
    wrapper = raw_config.get("env_wrapper")
    if wrapper is None:
        return None
    if not isinstance(wrapper, str) or not pathlib.Path(wrapper).is_absolute():
        raise GuardError("env_wrapper must be an absolute executable path")
    wrapper_path = pathlib.Path(wrapper)
    if not wrapper_path.is_file() or not os.access(wrapper_path, os.X_OK):
        raise GuardError("env_wrapper is not an executable file")

    command = [str(wrapper_path), sys.executable, str(pathlib.Path(__file__).resolve())]
    command.extend(argv)
    completed = subprocess.run(command, check=False)
    return completed.returncode


class RpcClient:
    def __init__(
        self,
        url: str,
        transport: Callable[[urllib.request.Request, float], bytes] | None = None,
    ) -> None:
        self.url = url
        self.transport = transport or self._urlopen
        self.request_id = 0

    @staticmethod
    def _urlopen(request: urllib.request.Request, timeout: float) -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            length_header = response.headers.get("Content-Length")
            if length_header and int(length_header) > MAX_RESPONSE_BYTES:
                raise GuardError("RPC response exceeds the size limit")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise GuardError("RPC response exceeds the size limit")
            return payload

    def call(self, method: str, params: list[Any]) -> Any:
        if method not in ALLOWED_METHODS:
            raise GuardError(f"RPC method is not allowed: {method}")
        self.request_id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params},
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "zeroclaw-wallet-guard/0.1"},
            method="POST",
        )
        try:
            payload = self.transport(request, 12.0)
            decoded = json.loads(payload)
        except GuardError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GuardError("RPC request failed") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GuardError("RPC returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise GuardError("RPC returned an invalid response shape")
        if decoded.get("error") is not None:
            error = decoded["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise GuardError(f"RPC returned an error (code={code})")
        if "result" not in decoded:
            raise GuardError("RPC response has no result")
        return decoded["result"]


def fetch_snapshot(config: GuardConfig, client: RpcClient) -> dict[str, Any]:
    balance_result = client.call(
        "getBalance", [config.wallet_address, {"commitment": config.commitment}]
    )
    signatures_result = client.call(
        "getSignaturesForAddress",
        [
            config.wallet_address,
            {"limit": config.max_signatures, "commitment": config.commitment},
        ],
    )
    tokens_result = client.call(
        "getTokenAccountsByOwner",
        [
            config.wallet_address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed", "commitment": config.commitment},
        ],
    )

    try:
        lamports = int(balance_result["value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GuardError("getBalance returned an invalid value") from exc

    if not isinstance(signatures_result, list):
        raise GuardError("getSignaturesForAddress returned an invalid value")
    safe_signatures: list[dict[str, Any]] = []
    for item in signatures_result[: config.max_signatures]:
        if not isinstance(item, dict) or not isinstance(item.get("signature"), str):
            continue
        safe_signatures.append(
            {
                "signature": item["signature"][:100],
                "slot": int(item.get("slot", 0)),
                "blockTime": item.get("blockTime") if isinstance(item.get("blockTime"), int) else None,
                "failed": item.get("err") is not None,
                "confirmationStatus": item.get("confirmationStatus")
                if item.get("confirmationStatus") in {"processed", "confirmed", "finalized"}
                else None,
            }
        )

    values = tokens_result.get("value") if isinstance(tokens_result, dict) else None
    if not isinstance(values, list):
        raise GuardError("getTokenAccountsByOwner returned an invalid value")
    tokens: dict[str, dict[str, Any]] = {}
    for account in values[: config.max_token_accounts]:
        try:
            info = account["account"]["data"]["parsed"]["info"]
            mint = validate_wallet_address(info["mint"])
            amount_info = info["tokenAmount"]
            amount = int(amount_info["amount"])
            decimals = int(amount_info["decimals"])
            if decimals < 0 or decimals > 30 or amount < 0:
                raise ValueError
        except (KeyError, TypeError, ValueError, GuardError):
            continue
        current = tokens.setdefault(mint, {"rawAmount": 0, "decimals": decimals})
        if current["decimals"] == decimals:
            current["rawAmount"] += amount

    return {
        "schemaVersion": 1,
        "observedAt": int(time.time()),
        "walletAddress": config.wallet_address,
        "lamports": lamports,
        "tokens": tokens,
        "signatures": safe_signatures,
        "signatureWindowSaturated": len(signatures_result) >= config.max_signatures,
        "tokenAccountsReturned": len(values),
        "tokenAccountsObserved": min(len(values), config.max_token_accounts),
        "tokenAccountsTruncated": len(values) > config.max_token_accounts,
    }


def read_previous_state(path: pathlib.Path, wallet_address: str) -> dict[str, Any] | None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardError("state file is not readable valid JSON") from exc
    if not isinstance(state, dict) or state.get("schemaVersion") != 1:
        raise GuardError("state file has an unsupported shape or schema")
    if state.get("walletAddress") != wallet_address:
        raise GuardError("state file wallet address does not match config")
    if (
        isinstance(state.get("lamports"), bool)
        or not isinstance(state.get("lamports"), int)
        or state["lamports"] < 0
        or not isinstance(state.get("tokens"), dict)
        or not isinstance(state.get("signatures"), list)
        or not isinstance(state.get("tokenAccountsTruncated"), bool)
    ):
        raise GuardError("state file has invalid snapshot fields")
    return state


def atomic_write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".wallet-guard-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def token_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    before = previous.get("tokens") if isinstance(previous.get("tokens"), dict) else {}
    after = current.get("tokens") if isinstance(current.get("tokens"), dict) else {}
    changes: list[dict[str, Any]] = []
    for mint in sorted(set(before) | set(after)):
        before_item = before.get(mint, {})
        after_item = after.get(mint, {})
        before_raw = int(before_item.get("rawAmount", 0))
        after_raw = int(after_item.get("rawAmount", 0))
        if before_raw == after_raw:
            continue
        decimals = int(after_item.get("decimals", before_item.get("decimals", 0)))
        divisor = Decimal(10) ** decimals
        changes.append(
            {
                "mint": mint,
                "rawDelta": after_raw - before_raw,
                "uiDelta": format(Decimal(after_raw - before_raw) / divisor, "f"),
                "decimals": decimals,
                "newMint": mint not in before,
                "removedMint": mint not in after,
            }
        )
    return changes


def build_report(
    config: GuardConfig, previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    signatures = current["signatures"]
    previous_signatures = {
        item.get("signature")
        for item in (previous or {}).get("signatures", [])
        if isinstance(item, dict)
    }
    new_signatures = [
        item for item in signatures if item["signature"] not in previous_signatures
    ]
    failed_new = [item for item in new_signatures if item["failed"]]
    signature_window_saturated = current.get("signatureWindowSaturated") is True
    signature_diff_reliable = not signature_window_saturated

    token_diff_reliable = (
        previous is None
        or (
            previous.get("tokenAccountsTruncated") is False
            and current["tokenAccountsTruncated"] is False
        )
    )

    if previous is None:
        sol_delta = 0
        changes: list[dict[str, Any]] = []
        status = "baseline"
    else:
        sol_delta = current["lamports"] - int(previous.get("lamports", 0))
        changes = token_changes(previous, current) if token_diff_reliable else []
        is_alert = (
            abs(sol_delta) >= config.sol_change_threshold_lamports
            or bool(changes)
            or bool(failed_new)
        )
        status = "alert" if is_alert else ("activity" if new_signatures else "no_change")

    return {
        "schemaVersion": 1,
        "status": status,
        "observedAt": current["observedAt"],
        "walletAddress": config.wallet_address,
        "balance": {
            "lamports": current["lamports"],
            "sol": format(Decimal(current["lamports"]) / Decimal(1_000_000_000), "f"),
            "deltaLamports": sol_delta,
            "deltaSol": format(Decimal(sol_delta) / Decimal(1_000_000_000), "f"),
            "alertThresholdSol": format(
                Decimal(config.sol_change_threshold_lamports) / Decimal(1_000_000_000), "f"
            ),
        },
        "activity": {
            "newSignatureCount": len(new_signatures),
            "newSignatureCountExact": signature_diff_reliable,
            "failedNewSignatureCount": len(failed_new),
            "newSignatures": new_signatures,
            "signatureWindowSaturated": signature_window_saturated,
            "signatureDiffReliable": signature_diff_reliable,
        },
        "tokenChanges": changes,
        "inventory": {
            "tokenMintCount": len(current["tokens"]),
            "tokenAccountsReturned": current["tokenAccountsReturned"],
            "tokenAccountsObserved": current["tokenAccountsObserved"],
            "tokenAccountsTruncated": current["tokenAccountsTruncated"],
            "tokenDiffReliable": token_diff_reliable,
        },
        "safety": {
            "custodyTier": "T0_READ_ONLY",
            "rpcMethodsUsed": sorted(ALLOWED_METHODS),
            "privateKeyAccess": False,
            "transactionConstruction": False,
            "transactionSigning": False,
            "transactionBroadcast": False,
            "untrustedTextFetched": False,
        },
    }


def scan(config: GuardConfig, save_state: bool = True) -> dict[str, Any]:
    previous = read_previous_state(config.state_path, config.wallet_address)
    current = fetch_snapshot(config, RpcClient(config.rpc_url))
    report = build_report(config, previous, current)
    if save_state:
        atomic_write_json(config.state_path, current)
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan", help="scan and compare with prior state")
    scan_parser.add_argument("--config", required=True, type=pathlib.Path)
    scan_parser.add_argument("--no-save", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(actual_argv)
    try:
        config_path = args.config.expanduser().resolve()
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise GuardError("config file is not readable JSON") from exc
        wrapper_result = maybe_run_through_wrapper(raw, config_path, actual_argv)
        if wrapper_result is not None:
            return wrapper_result
        config, _ = load_config(config_path)
        report = scan(config, save_state=not args.no_save)
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return 0
    except GuardError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
