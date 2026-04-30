# Examples

Examples use synthetic data only.

Create and inspect the dependency-trap demo:

```powershell
uv run nmsl --root .tmp/demo-ledger demo --name three-claim-dependency --layer full
uv run nmsl --root .tmp/demo-ledger validate
uv run nmsl --root .tmp/demo-ledger doctor
uv run nmsl --root .tmp/demo-ledger audit
uv run nmsl --root .tmp/demo-ledger explain A
uv run nmsl --root .tmp/demo-ledger state
```

Create the overload demo:

```powershell
uv run nmsl --root .tmp/flood-ledger demo --name acceptance-flood --layer standard
uv run nmsl --root .tmp/flood-ledger doctor
uv run nmsl --root .tmp/flood-ledger audit
```

Create a small custom ledger:

```powershell
uv run nmsl --root .tmp/custom-ledger init --layer full
uv run nmsl --root .tmp/custom-ledger config set active_capacity 5
uv run nmsl --root .tmp/custom-ledger config set reserve_caps.replay 2
uv run nmsl --root .tmp/custom-ledger claim add claim:1 --title "Synthetic claim" --family-id demo --frontier-bucket default
uv run nmsl --root .tmp/custom-ledger evidence add claim:1 --uri "https://example.org/artifact.json" --sha256 "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" --size 64
uv run nmsl --root .tmp/custom-ledger replay
uv run nmsl --root .tmp/custom-ledger doctor
```

The `.tmp/` directory is intentionally ignored by Git.
