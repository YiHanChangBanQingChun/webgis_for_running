import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.derive import activity_summary, calendar_rows
from app import main


def archive(start, field_type=None):
    message = dict(message_type='session', fields=dict(start_time=start, sport='running', total_distance=1000, total_timer_time=300))
    if field_type:
        message['field_metadata'] = {'start_time': {'type': field_type}}
    return dict(activity_id='480751026543034372', source={'path':'x.fit'}, parse={'status':'complete','error':None}, messages=[message])


class MigrationTests(unittest.TestCase):
    def test_spec_utc_rolls_into_next_chinese_day(self):
        result = activity_summary(archive('2026-10-01T22:00:00', '<FieldType: date_time (...)>'))
        self.assertEqual(result['date'], '2026-10-02')
        self.assertEqual(result['start_time'], '2026-10-01T22:00:00+00:00')
        self.assertEqual(result['original_start_time'], '2026-10-01T22:00:00')

    def test_unknown_naive_timestamp_is_not_assigned_timezone(self):
        result = activity_summary(archive('2026-10-01T22:00:00'))
        self.assertEqual(result['date'], '2026-10-01')
        self.assertEqual(result['timezone_evidence'], 'unknown_timezone_retained_original')

    def test_local_date_time_is_not_utc(self):
        result = activity_summary(archive('2026-10-01T22:00:00', 'local_date_time'))
        self.assertEqual(result['date'], '2026-10-01')

    def test_explicit_offset_is_independent_of_machine_timezone(self):
        result = activity_summary(archive('2026-10-01T14:00:00-07:00'))
        self.assertEqual(result['date'], '2026-10-02')

    def test_calendar_keeps_mixed_record_without_counting_distance(self):
        item = dict(date='2026-10-02',id='test',distance_m=7000,elapsed_s=2700,calories=300,training_excluded=True)
        result = calendar_rows([item])[0]
        self.assertEqual(result['distance_m'], 0)
        self.assertEqual(result['activity_ids'], ['test'])

    def test_running_statistics_exclude_riding_and_hiking(self):
        base = dict(date='2026-10-02',elapsed_s=300,average_heart_rate=140,total_ascent_m=0,calories=0)
        rows = [dict(base,id='run',sport='running',distance_m=1000),
                dict(base,id='mixed',sport='running',distance_m=7000,training_excluded=True),
                dict(base,id='hike',sport='hiking',distance_m=15000)]
        with patch.object(main, '_assert_ready'), patch.object(main, '_activities', return_value=rows):
            result = main.range_stats('2026-10-02','2026-10-02')
        self.assertEqual(result['summary']['activity_count'], 1)
        self.assertEqual(result['summary']['total_distance_m'], 1000)


if __name__ == '__main__':
    unittest.main()
