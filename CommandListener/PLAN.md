# Standalone TCE State Output via QA SOAP Pull Fallback

## Summary
- Keep `CommandListener.py` in `--mode tce`, but make it self-sufficient by adding a QA SOAP pull path for game state.
- Continue hosting the existing TCE callback listener and endpoint registration, but stop depending on inbound push callbacks for terminal state output.
- Emit the same terminal payload format for standalone state changes: `tceNumber|3||STATE|<state>`.

## Key Changes
- In `CommandListener.py`, add QA SOAP helper(s) for `GetGameState` and a one-time `InitTestClient` bootstrap using the existing `send_soap_request` and `parse_soap_body_operation` utilities.
- Add a small internal `TCEStatePoller` loop that starts immediately after successful TCE endpoint registration.
- Poll the QA service every `250 ms`, emit only when the non-empty state changes, and ignore blank state responses.
- Use `InitTestClient` once at startup to seed the initial state if it is available, then use `GetGameState` for steady-state polling.
- Refactor `TCEOutputSession` so state emission is shared across callback and pull sources, with de-duplication by last emitted state.
- Preserve existing idle semantics: if a non-idle state was emitted first and the next changed state is `MarketWrapperReelStateMachine::Idle`, emit it once and allow the existing stop behavior to fire.
- Keep callback handling enabled; if push callbacks ever arrive, they should still print, but the shared de-dup logic must prevent double-printing when pull and push report the same state.
- Update the 30-second “no callback” warning logic so it only warns when neither callback traffic nor pull-based state retrieval produced usable gameplay state.
- If pull is working but callbacks are silent, do not print the current firewall-style warning; optionally log a debug/info note that standalone pull mode is active.
- Keep scope tight to game-state output only for v1; do not add polling for bank, bet, paylines, or game-info terminal lines yet.

## Public Interface
- No new mode or required CLI flags in v1.
- `--mode tce` automatically gains standalone state polling behavior.
- `--mode sas` stays unchanged and continues to print generic SAS events, not named game states.

## Test Plan
- Add helper tests for parsing `GetGameStateResponse` and `InitTestClientResponse`.
- Add sequence tests for `blank -> state A -> repeated state A -> Idle`, asserting only changed non-empty states are emitted and idle triggers the existing stop behavior after prior activity.
- Add cross-source tests where a callback emits state A and the puller sees state A on the next tick, asserting only one terminal line is printed.
- Add warning-behavior tests for:
  1. callbacks absent, pull succeeds with usable states,
  2. callbacks absent, pull returns only blanks,
  3. callbacks absent, pull raises transient SOAP errors.
- Keep existing self-probe, callback parsing, and `SetTCEEndPoint` / `GetTCEEndPoint` tests passing.

## Assumptions
- This plan is based on the live environment as of Monday, August 10, 2026: the QA SOAP service at `http://172.22.51.108:18081` responds successfully, and `GetGameState` is callable even though callback pushes are currently absent.
- Standalone means “no `TCE.exe` and no `VLT_Connect.dll` dependency at runtime”; it is still acceptable to use the existing QA SOAP service exposed by the VLT.
- Blank `GetGameState` responses should be treated as “no usable state yet,” not as a terminal state transition.
