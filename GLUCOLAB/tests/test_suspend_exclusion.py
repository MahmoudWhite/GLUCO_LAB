"""Synthetic pump data tests: exclude suspensions from candidate basal schedules."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import analyze_files


def libre(end="06/11/2026 09:50:00"):
    return ("metadata\nDevice Timestamp,Record Type,Historic Glucose (mg/dL)\n"
            + f"{end},0,155\n").encode()


def pump(rows):
    return ("metadata\nDate,Time,Basal Rate (U/h),Suspend,Rewind\n" +
            "\n".join(f"{d},{t},{r},{s},{rew}" for d,t,r,s,rew in rows) +"\n").encode()


def rate(date,t,r):
    return (date,t,str(r),"","")


class SuspendExclusionTests(unittest.TestCase):
    def test_four_minute_zero_rate_suspend_is_not_a_new_range(self):
        before = [rate('2026/11/04',t,r) for t,r in [
            ('00:00:00',1.75),('03:00:00',1.95),('07:00:00',2.30),
            ('12:30:00',2.35),('14:30:00',2.50),('16:30:00',2.50),('20:00:00',2.40)]]
        target = [rate('2026/11/05',t,r) for t,r in [
            ('00:00:00',1.75),('03:00:00',1.95),('07:00:00',2.30),
            ('12:30:00',2.35),('14:30:00',2.50),('16:30:00',2.50),('20:00:00',2.40)]]
        target += [
            ('2026/11/05','22:11:16','0','NOTSEATED_SUSPEND',''),
            ('2026/11/05','22:11:55','0','','Rewind'),
            ('2026/11/05','22:15:52','2.4','NORMAL_PUMPING',''),
        ]
        after = [rate('2026/11/06','00:00:00',1.75),rate('2026/11/06','03:00:00',1.90),rate('2026/11/06','07:00:00',2.30)]
        result = analyze_files(libre(),pump(before+target+after))
        pattern = result['pattern']
        self.assertEqual(pattern['profile_day'],'2026-11-05')
        self.assertEqual([(x['start'],x['end']) for x in pattern['segments']], [
            ('00:00','03:00'),('03:00','07:00'),('07:00','12:30'),
            ('12:30','14:30'),('14:30','20:00'),('20:00','24:00')])
        self.assertEqual(pattern['excluded_rate_entries'],3)
        self.assertEqual(pattern['suspension_events_on_day'],2)
        self.assertNotIn('22:11–22:15',result['report'])

    def test_most_recent_complete_day_wins_over_older_noisy_day(self):
        older=[rate('2026/11/04',t,r) for t,r in [
            ('00:00:00',1.0),('03:00:00',1.2),('07:00:00',1.4),
            ('10:00:00',1.5),('12:30:00',1.6),('14:30:00',1.7),
            ('16:30:00',1.8),('20:00:00',1.9)]]
        newer=[rate('2026/11/05',t,r) for t,r in [
            ('00:00:00',1.1),('03:00:00',1.3),('07:00:00',1.5),
            ('20:00:00',1.8)]]
        result=analyze_files(libre(),pump(older+newer))
        self.assertEqual(result['pattern']['profile_day'],'2026-11-05')
        self.assertEqual(len(result['pattern']['segments']),4)

    def test_does_not_use_pump_day_after_glucose_end(self):
        earlier=[rate('2026/11/05',t,r) for t,r in [
            ('00:00:00',1.0),('03:00:00',1.2),('07:00:00',1.3),('20:00:00',1.5)]]
        later=[rate('2026/11/16',t,r) for t,r in [
            ('00:00:00',2.0),('03:00:00',2.2),('07:00:00',2.3),('20:00:00',2.5)]]
        result=analyze_files(libre(),pump(earlier+later))
        self.assertEqual(result['pattern']['profile_day'],'2026-11-05')
        self.assertEqual(result['pattern']['segments'][0]['original_rate'],1.0)


if __name__ == '__main__':
    unittest.main()
