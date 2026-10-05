# Changelog

## 2026-10-05: Part 1, Django shop-floor terminal (contract 002)

- Django 6.1 terminal (`ERP/portal`, http://localhost:8081): operators sign in, pick a workstation, and Start / Pause / Resume / Complete job cards and log defects; everything is written to ERPNext through REST v2.
- Queue with Running / Paused / Ready / Waiting status and Overdue / Today / Later labels; paused cards complete in one step; server-side guards against double starts.
- ERPNext side: 4 operator Employees and a least-privilege API role ("Shop Floor Terminal") with the key/secret from site config.
- 63 Django tests (unit + live contract tests against a separate ERPNext site) and 32 ERPNext tests. Lighthouse mobile 100/100/100.
- Independent code, security, alignment, integration, browser and design validation: all PASS after two recovery rounds (a paused card could not be completed; a scratch file with a test-site admin token had reached the image and was removed and the key rotated).
- Stack: nginx and the realtime service now follow backend restarts.

## 2026-10-04: Part 1, factory ERP (contract 001)

- ERPNext v16 Docker stack (adapted from frappe_docker `pwd.yml`; realtime works on localhost, port bound to 127.0.0.1).
- `ombak_mfg` app: Defect Log and Defect Reason doctypes; Work Order On-Time Rate, Workstation Load, Operation Time Variance and Defect Pareto reports; daily overdue-work-order alert; Ombak Factory workspace with 3 number cards.
- Idempotent master-data setup and a one-month demo-data generator (sales order → production plan/MRP → purchasing with inspection → work orders and job cards → delivery trip → invoice), plus a demo smoke check.
- 29 integration tests. Independent code, security, alignment and browser validation: all PASS.
