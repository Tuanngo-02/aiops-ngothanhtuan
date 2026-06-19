# Báo cáo nghiệm thu (Submit)

Dưới đây là không gian để dán log đầu ra của Orchestrator khi chạy các kịch bản kiểm thử:

## Scenario 1 — Action succeeds
```json
{"ts": 1781841148.482118, "event_type": "ALERT_DETECTED", "service": "payment-svc", "action": "HighLatency", "result": "detect"}
{"ts": 1781841148.6644764, "event_type": "DRY_RUN_PASS", "service": "payment-svc", "action": "HighLatency", "result": "dry_run"}
{"ts": 1781841148.6655834, "event_type": "RUNBOOK_EXEC", "service": "payment-svc", "action": "HighLatency", "result": "runbooks/restart_service.sh"}
{"ts": 1781841159.8412423, "event_type": "VERIFY_START", "service": "payment-svc", "action": "HighLatency", "result": "verify"}
{"ts": 1781841190.003568, "event_type": "ACTION_SUCCESS", "service": "payment-svc", "action": "HighLatency", "result": "runbooks/restart_service.sh"}
```

## Scenario 2 — Action fails → rollback
```json
{"ts": 1781842361.4107745, "event_type": "ALERT_DETECTED", "service": "checkout-svc", "action": "InstanceDown", "result": "detect"}
{"ts": 1781842361.5512185, "event_type": "DRY_RUN_PASS", "service": "checkout-svc", "action": "InstanceDown", "result": "dry_run"}
{"ts": 1781842361.5522044, "event_type": "RUNBOOK_EXEC", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842362.21613, "event_type": "VERIFY_START", "service": "checkout-svc", "action": "InstanceDown", "result": "verify"}
{"ts": 1781842482.7761955, "event_type": "VERIFY_FAIL", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842482.7772257, "event_type": "ROLLBACK_TRIGGERED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842493.960207, "event_type": "ROLLBACK_EXECUTED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/rollback_restart.sh"}
```

## Scenario 3 — Circuit breaker
```json
{"ts": 1781842361.4107745, "event_type": "ALERT_DETECTED", "service": "checkout-svc", "action": "InstanceDown", "result": "detect"}
{"ts": 1781842361.5512185, "event_type": "DRY_RUN_PASS", "service": "checkout-svc", "action": "InstanceDown", "result": "dry_run"}
{"ts": 1781842361.5522044, "event_type": "RUNBOOK_EXEC", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842362.21613, "event_type": "VERIFY_START", "service": "checkout-svc", "action": "InstanceDown", "result": "verify"}
{"ts": 1781842482.7761955, "event_type": "VERIFY_FAIL", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842482.7772257, "event_type": "ROLLBACK_TRIGGERED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842493.960207, "event_type": "ROLLBACK_EXECUTED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/rollback_restart.sh"}
{"ts": 1781842721.9056563, "event_type": "ALERT_DETECTED", "service": "checkout-svc", "action": "InstanceDown", "result": "detect"}
{"ts": 1781842722.0441093, "event_type": "DRY_RUN_PASS", "service": "checkout-svc", "action": "InstanceDown", "result": "dry_run"}
{"ts": 1781842722.0441093, "event_type": "RUNBOOK_EXEC", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842722.6819007, "event_type": "VERIFY_START", "service": "checkout-svc", "action": "InstanceDown", "result": "verify"}
{"ts": 1781842843.1744027, "event_type": "VERIFY_FAIL", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842843.175417, "event_type": "ROLLBACK_TRIGGERED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842854.3738773, "event_type": "ROLLBACK_EXECUTED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/rollback_restart.sh"}
{"ts": 1781842962.1760662, "event_type": "ALERT_DETECTED", "service": "checkout-svc", "action": "InstanceDown", "result": "detect"}
{"ts": 1781842962.3233163, "event_type": "DRY_RUN_PASS", "service": "checkout-svc", "action": "InstanceDown", "result": "dry_run"}
{"ts": 1781842962.3233163, "event_type": "RUNBOOK_EXEC", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781842962.9690914, "event_type": "VERIFY_START", "service": "checkout-svc", "action": "InstanceDown", "result": "verify"}
{"ts": 1781843083.4096718, "event_type": "VERIFY_FAIL", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781843083.4106865, "event_type": "ROLLBACK_TRIGGERED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/restart_service.sh"}
{"ts": 1781843094.5632994, "event_type": "ROLLBACK_EXECUTED", "service": "checkout-svc", "action": "InstanceDown", "result": "runbooks/rollback_restart.sh"}
{"ts": 1781843094.5644147, "event_type": "CIRCUIT_OPEN", "service": "checkout-svc", "action": "InstanceDown", "result": "halt"}
```

## Stress Test 4 — Multi-step transactional rollback
*(Dán log ở đây)*
```json
{"ts": 1781843757.3640594, "event_type": "ALERT_DETECTED", "service": "api-gateway", "action": "InstanceDown", "result": "detect"}
{"ts": 1781843757.800387, "event_type": "DRY_RUN_PASS", "service": "api-gateway", "action": "InstanceDown", "result": "dry_run"}
{"ts": 1781843757.8013747, "event_type": "RUNBOOK_EXEC", "service": "api-gateway", "action": "InstanceDown", "result": "runbooks/step_a.sh"}
{"ts": 1781843757.9898689, "event_type": "RUNBOOK_EXEC", "service": "api-gateway", "action": "InstanceDown", "result": "runbooks/step_b.sh"}
{"ts": 1781843758.2963462, "event_type": "RUNBOOK_EXEC", "service": "api-gateway", "action": "InstanceDown", "result": "runbooks/step_c.sh"}
{"ts": 1781843758.4587052, "event_type": "TRANSACTIONAL_STEP_FAIL", "service": "api-gateway", "action": "InstanceDown", "result": "runbooks/step_c.sh", "completed_before_failure": ["runbooks/step_a.sh", "runbooks/step_b.sh"]}
{"ts": 1781843758.4587052, "event_type": "TRANSACTIONAL_ROLLBACK_STEP", "service": "api-gateway", "action": "InstanceDown", "result": "runbooks/rollback_b.sh"}
{"ts": 1781843758.6019146, "event_type": "TRANSACTIONAL_ROLLBACK_STEP", "service": "api-gateway", "action": "InstanceDown", "result": "runbooks/rollback_a.sh"}
{"ts": 1781843758.755154, "event_type": "TRANSACTIONAL_ROLLBACK_COMPLETE", "service": "api-gateway", "action": "InstanceDown", "result": "rollback", "rolled_back": ["runbooks/rollback_b.sh", "runbooks/rollback_a.sh"]}
```

## Stress Test 5 — Concurrent alert race
```json
{"ts": 1781845049.0403337, "event_type": "ALERT_DETECTED", "service": "payment-svc", "action": "HighLatency", "result": "detect"}
{"ts": 1781845049.2311745, "event_type": "DRY_RUN_PASS", "service": "payment-svc", "action": "HighLatency", "result": "dry_run"}
{"ts": 1781845049.2317214, "event_type": "RUNBOOK_EXEC", "service": "payment-svc", "action": "HighLatency", "result": "runbooks/restart_service.sh"}
{"ts": 1781845060.3967848, "event_type": "VERIFY_START", "service": "payment-svc", "action": "HighLatency", "result": "verify"}
{"ts": 1781845070.4871447, "event_type": "ACTION_SUCCESS", "service": "payment-svc", "action": "HighLatency", "result": "runbooks/restart_service.sh"}
{"ts": 1781845094.0964596, "event_type": "ALERT_DETECTED", "service": "inventory-svc", "action": "HighLatency", "result": "detect"}
{"ts": 1781845094.2470162, "event_type": "DRY_RUN_PASS", "service": "inventory-svc", "action": "HighLatency", "result": "dry_run"}
{"ts": 1781845094.2470162, "event_type": "RUNBOOK_EXEC", "service": "inventory-svc", "action": "HighLatency", "result": "runbooks/restart_service.sh"}
{"ts": 1781845105.5064464, "event_type": "VERIFY_START", "service": "inventory-svc", "action": "HighLatency", "result": "verify"}
{"ts": 1781845115.5824816, "event_type": "ACTION_SUCCESS", "service": "inventory-svc", "action": "HighLatency", "result": "runbooks/restart_service.sh"}
```

## Stress Test 6 — LLM hallucination defense
*(Dán log ở đây)*
```json

```
