FROM frappe/erpnext:v16.37.0

COPY --chown=frappe:frappe apps/ombak_mfg /home/frappe/frappe-bench/apps/ombak_mfg
RUN cd /home/frappe/frappe-bench && ./env/bin/pip install --no-cache-dir -e apps/ombak_mfg
