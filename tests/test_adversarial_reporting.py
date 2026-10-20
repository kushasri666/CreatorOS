"""Evaluation must expose failures and evaluate the requested content format."""
import unittest
from content_quality import score
from scripts.validate_saved_brands import outcome


class AdversarialReportingTests(unittest.TestCase):
    def test_failed_media_return_cannot_be_a_pass(self):
        self.assertEqual(outcome({}),'failed')
        self.assertEqual(outcome(dict(video_status='failed',bytes=0,scheduling_status='ready_to_publish')),'failed')
    def test_empty_ready_video_and_unfinished_handoff_are_failures(self):
        self.assertEqual(outcome(dict(video_status='ready',bytes=0,scheduling_status='ready_to_publish')),'failed')
        self.assertEqual(outcome(dict(video_status='ready',bytes=2000,scheduling_status='scheduled')),'failed')
    def test_needs_review_is_preserved_and_successful_media_can_pass(self):
        self.assertEqual(outcome(dict(approved=False,status='needs_review')),'needs_review')
        self.assertEqual(outcome(dict(video_status='ready',bytes=2000,scheduling_status='feedback_recorded')),'passed')
    def test_empty_carousel_cannot_receive_perfect_format_score(self):
        requirements=dict(concepts=[['AI']],cta_terms=['save'],voice_terms=['AI'],slide_count=4)
        result=score(dict(text='Learn practical AI content habits. Save this guide.',slides=[]),'instagram',requirements)
        self.assertFalse(result['checks']['carousel_structure']['passed'])
        self.assertLess(result['score_100'],100)
    def test_duplicate_slides_and_prose_disguised_as_video_are_penalized(self):
        result=score(dict(text='Learn practical AI content habits. Save this guide.',slides=['Learn practical AI content habits']*4),
            'instagram',dict(concepts=[['AI']],cta_terms=['save'],slide_count=4))
        self.assertFalse(result['checks']['carousel_structure']['passed'])
        result=score(dict(text='Learn practical AI content habits. Save this guide.',slides=[]),'youtube',
            dict(concepts=[['AI']],cta_terms=['save'],format='short_script'))
        self.assertFalse(result['checks']['script_format']['passed'])
