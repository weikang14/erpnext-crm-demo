from datetime import UTC, datetime

from django.test import SimpleTestCase

from terminal import queue


class TimeTests(SimpleTestCase):
    def test_erpnext_gets_kuala_lumpur_wall_clock(self):  # ACT-1, FM1
        self.assertEqual(queue.erp_now(datetime(2026, 10, 5, 6, 30, tzinfo=UTC)), "2026-10-05 14:30:00")

    def test_elapsed_counts_closed_and_open_logs(self):
        now = datetime(2026, 10, 5, 6, 30, tzinfo=UTC)  # 14:30 in Kuala Lumpur
        job = {"total_time_in_mins": 30, "time_logs": [{"from_time": "2026-10-05 14:00:00", "to_time": None}]}
        self.assertEqual(queue.elapsed_seconds(job, now), 30 * 60 + 30 * 60)

    def test_planned_window(self):
        def card(start, end):
            return queue.Card("PO-JOB00001", "WO", "Op", "Item", 1, 1, queue.parse_erp(start), queue.parse_erp(end), "ready")

        self.assertEqual(card("2026-10-05 08:00:00", "2026-10-05 11:20:00").planned_window, "Mon 5 Oct, 08:00–11:20")
        self.assertEqual(
            card("2026-09-28 16:37:00", "2026-09-29 09:45:00").planned_window, "Mon 28 Sep 16:37 – Tue 29 Sep 09:45"
        )

    def test_elapsed_display(self):
        card = queue.Card("PO-JOB00001", "WO", "Op", "Item", 1, 1, None, None, "running", elapsed_seconds=3725)
        self.assertEqual(card.elapsed_display, "01:02:05")
