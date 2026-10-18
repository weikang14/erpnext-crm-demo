# Event Catalog

Not applicable: the CRM has no async events, queues, pub/sub or job runner (only gunicorn, `CRM/Dockerfile:12`). ombak_mfg has no `doc_events` (`ERP/apps/ombak_mfg/ombak_mfg/hooks.py:147` is commented out). Its only scheduled job is the daily overdue-WO alert (`hooks.py:269-271`, `tasks.py:12-65`), which 004 does not touch. Whether 004 adds an after-commit or background step is open question 1.
