import unittest

from update_stats import ProfileCalendar


class ProfileCalendarTests(unittest.TestCase):
    def parse(self, html):
        parser = ProfileCalendar()
        parser.feed(html)
        return parser.days()

    def test_counts_follow_tooltip_ids_and_dates_not_html_order(self):
        days = self.parse('''
          <td data-date="2026-11-13" id="b"></td>
          <td id="a" data-date="2026-11-12"></td>
          <tool-tip for="a">No contributions on November 12th.</tool-tip>
          <tool-tip for="b">1,234 contributions on November 13th.</tool-tip>
        ''')
        self.assertEqual(days, [
            {'date': '2026-11-12', 'contributionCount': 0},
            {'date': '2026-11-13', 'contributionCount': 1234},
        ])

    def test_incomplete_calendar_fails_instead_of_changing_streak(self):
        for html in [
            '',
            '<td data-date="2026-11-12" id="a"></td>',
            '<td data-date="2026-11-12" id="a"></td><tool-tip for="a">Changed markup</tool-tip>',
            '''<td data-date="2026-11-11" id="a"></td>
               <td data-date="2026-11-13" id="b"></td>
               <tool-tip for="a">1 contribution on November 11th.</tool-tip>
               <tool-tip for="b">1 contribution on November 13th.</tool-tip>''',
        ]:
            with self.subTest(html=html), self.assertRaises(ValueError):
                self.parse(html)


if __name__ == '__main__':
    unittest.main()
