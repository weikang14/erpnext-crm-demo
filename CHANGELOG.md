# Changelog

## 2026-10-04: Part 1, factory ERP (contract 001)

- ERPNext v16 Docker stack (adapted from frappe_docker `pwd.yml`; realtime works on localhost, port bound to 127.0.0.1).
- `ombak_mfg` app: Defect Log and Defect Reason doctypes; Work Order On-Time Rate, Workstation Load, Operation Time Variance and Defect Pareto reports; daily overdue-work-order alert; Ombak Factory workspace with 3 number cards.
- Idempotent master-data setup and a one-month demo-data generator (sales order → production plan/MRP → purchasing with inspection → work orders and job cards → delivery trip → invoice), plus a demo smoke check.
- 29 integration tests. Independent code, security, alignment and browser validation: all PASS.
