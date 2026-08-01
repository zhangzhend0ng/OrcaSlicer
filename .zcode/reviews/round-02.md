# Round 02 — `need_slot` dangling pointer

Harness: UB-3 (out-of-bounds / vector realloc), UB-4 (use-after-move/free).
File: FulfillmentSliceMapping.cpp:64-81.

## Finding
`need_slot` was declared `-> const DeviceFilamentRow*` and returned `&rows.back()`
right after `rows.push_back(std::move(r))`. `push_back` may reallocate `rows`, so
the returned address is potentially dangling. The sole caller (Pass 1 loop, line 107)
discards the return value — so the dangling pointer was never dereferenced, but:
1. The dead return is a latent trap: any future caller storing it would hit UB.
2. It reads as if the function's contract is to return a stable row handle, which
   it cannot honour across subsequent `push_back`s in the same loop.

## Fix
Return `void`. The "already collected" early-out now `return;`s instead of returning
`&r`. Behaviour identical (rows built the same way); the dangling-pointer hazard is
removed structurally.

## Adversarial re-check
- Does any other caller of `need_slot` exist? No — `grep need_slot` shows only the
  definition + the one Pass-1 call. Safe to change signature.
- Does `rows` get reallocated between this lambda and the sort at line 112? No —
  `rows` is only mutated inside `need_slot`; after Pass 1 it's consumed read-only.
- Does removing the return change `rows` ordering/content? No — push_back order is
  unchanged; the dedup scan is unchanged.

## Verdict: APPROVE (fix applied), build pending.
