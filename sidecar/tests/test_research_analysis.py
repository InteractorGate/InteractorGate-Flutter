import copy
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'research'))
from manual_example import example
from text_protocol import Bigram, split_sentences, token_metrics, word_accuracy
from research_stats import nap, percentile, randomization_test, satisfaction, wilcoxon_paired
from study_analysis import load_e2, summarize_e2, summarize_e1_analysis
from analyze_study import questionnaire_rows


class StatisticsTests(unittest.TestCase):
    def test_manual_nap_ties_and_linear_percentile(self):
        self.assertEqual(nap([10,20],[5,15]),.75)
        self.assertEqual(nap([10],[10]),.5)
        self.assertEqual(percentile([100,300]),290)
        self.assertIsNone(nap([],[1]))

    def test_exact_wilcoxon_with_ties_and_zero_differences(self):
        result=wilcoxon_paired([4,5,6,7],[1,2,3,4])
        self.assertEqual(result['p_two_sided'],.125)
        self.assertEqual(result['statistic'],0)
        self.assertEqual(wilcoxon_paired([1,2],[1,2])['p_two_sided'],1)
        self.assertEqual(wilcoxon_paired([1,4,5],[1,2,3])['n_nonzero'],2)

    def test_randomization_uses_only_supplied_allocations(self):
        patterns=[[i in c for i in range(4)] for c in itertools.combinations(range(4),2)]
        result=randomization_test([10,20,5,15],[False,False,True,True],patterns)
        self.assertAlmostEqual(result['p_two_sided'],2/3)
        with self.assertRaises(ValueError):
            randomization_test([10,20],[False,True],[[False,True]])

    def test_questionnaire_scoring_and_missing_values_are_explicit(self):
        result=satisfaction([4,2]*5,[4]*8+[3]*4)
        self.assertEqual(result['sus_score'],75)
        self.assertAlmostEqual(result['quest_total_mean'],11/3)
        self.assertIsNone(satisfaction([None]+[3]*9,[None]*12)['sus_score'])
        self.assertIsNone(satisfaction([None]*10,[None]*12)['quest_total_mean'])
        with self.assertRaises(ValueError):
            satisfaction([0]+[3]*9,[4]*12)


class TextTests(unittest.TestCase):
    def test_split_has_no_normalized_sentence_overlap(self):
        split=split_sentences([['word',str(i)] for i in range(100)]+[['word','0']])
        self.assertEqual([len(split[k]) for k in ('train','validation','test')],[70,15,15])
        self.assertFalse(set(split['train'])&set(split['test']))
        self.assertFalse(set(split['validation'])&set(split['test']))
        self.assertEqual(split,split_sentences([['word',str(i)] for i in range(100)]))

    def test_bigram_is_smoothed_and_probability_mass_sums_to_one(self):
        model=Bigram(6,0,1,1).fit([[1,4,2],[1,4,5,2]])
        probabilities=model.probabilities(4)
        self.assertAlmostEqual(sum(probabilities.values()),1)
        self.assertGreater(probabilities[2],probabilities[3])
        self.assertAlmostEqual(sum(model.probabilities(99).values()),1)

    def test_oov_is_never_counted_as_a_correct_surface_word(self):
        rows=[(3,{2:.1,3:.8,4:.1}),(4,{2:.1,3:.1,4:.8}),(2,{2:.9,3:.05,4:.05})]
        self.assertEqual(word_accuracy(rows,[4],2,3)['word_top1'],.5)
        self.assertEqual(word_accuracy(rows,[4],2,3)['word_oov'],1)
        self.assertEqual(token_metrics(rows)['top1'],1)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)/'example'
        self.manifest=example(self.folder)
        self.entry={'path':self.folder/'manual_export.json','cohort':'pilot','environment':'synthetic','prediction_policy':'next_words_v1'}

    def tearDown(self):
        self.temp.cleanup()

    def test_export_matches_independently_calculated_manual_oracle(self):
        rows,diagnostics=load_e2([self.entry])
        result=summarize_e2(rows,json.loads(self.manifest.read_text(encoding='utf-8'))['randomizations'])[0]
        self.assertEqual(result['eligible_trials'],4)
        self.assertEqual(result['without']['median_duration_s'],15)
        self.assertEqual(result['with']['median_duration_s'],10)
        self.assertEqual(result['without']['median_composition_selections'],6)
        self.assertEqual(result['with']['median_composition_selections'],4)
        self.assertEqual(result['without']['median_characters_per_minute'],27)
        self.assertEqual(result['with']['median_characters_per_minute'],48)
        self.assertAlmostEqual(result['with']['median_ksr_literal_baseline'],1/3)
        self.assertEqual(result['nap_duration_lower_better'],.75)
        self.assertEqual(result['nap_selections_lower_better'],1)
        self.assertEqual(result['latency_p95_primary_shown_ms'],290)
        self.assertAlmostEqual(result['randomization']['p_two_sided'],2/3)
        self.assertEqual(questionnaire_rows(self.folder/'manual_questionnaires.csv')[0]['sus_score'],75)
        self.assertEqual(diagnostics[0]['problems'],[])

    def test_repeated_exports_do_not_duplicate_trials_and_conflicts_are_rejected(self):
        rows,_=load_e2([self.entry,self.entry])
        self.assertEqual(len(rows),4)
        other=copy.deepcopy(json.loads(self.entry['path'].read_text()))
        other['logs'][0]['timestamp']='changed'
        path=self.folder/'conflict.json'
        path.write_text(json.dumps(other))
        with self.assertRaises(ValueError):
            load_e2([self.entry,{**self.entry,'path':path}])

    def test_practice_and_incorrect_transcription_are_not_primary_results(self):
        value=json.loads(self.entry['path'].read_text())
        for event in value['logs']:
            if 'data' in event:
                event['data'].update(practice=True,protocol_session='practice')
        self.entry['path'].write_text(json.dumps(value))
        rows,_=load_e2([self.entry])
        self.assertTrue(all(not r['analysis_eligible'] and 'practice' in r['exclusion_reasons'] for r in rows))
        self.assertIsNone(summarize_e2(rows)[0]['nap_duration_lower_better'])
        for event in value['logs']:
            if event['event_type']=='trial_end':
                event['data']['final_text']='incorrecto'
        self.entry['path'].write_text(json.dumps(value))
        rows,_=load_e2([self.entry])
        self.assertTrue(all('final_text_not_reconstructed' in r['exclusion_reasons'] for r in rows))

    def test_sequence_gap_excludes_trials_and_unverified_randomization_stays_missing(self):
        value=json.loads(self.entry['path'].read_text())
        value['logs'].pop(0)
        value['count']-=1
        self.entry['path'].write_text(json.dumps(value))
        rows,_=load_e2([self.entry])
        self.assertTrue(all('session_sequence_gap_or_duplicate' in r['exclusion_reasons'] for r in rows))
        self.assertIsNone(summarize_e2(rows)[0]['randomization'])


class E1AnalysisTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for engine,values in [('gazecnn_generic',[4,5,6]),('mediapipe_ridge_calibrated',[1,2,3])]:
            for i,value in enumerate(values):
                rows.append({'participant_code':'DEMO','cohort':'pilot','root_session_id':'root','condition_id':'c1',
                             'engine':engine,'phase':'angular','attempted':True,'exclusion_reasons':'',
                             'target_id':f'p{i}','repetition':1,'angular_mean_screen_deg':value,
                             '_geometry':{'eye_screen_distance_mm':600},'_instrument':'e1-v1','_cnn_hash':'same',
                             '_trial':{'target':{'point':[.2+i*.3,.5]}}})
        return rows

    def test_paired_test_requires_identical_geometry_and_preserves_missing_inference(self):
        rows=self.rows()
        self.assertEqual(summarize_e1_analysis(rows)[0]['wilcoxon']['p_two_sided'],.25)
        rows[-1]['_geometry']={'eye_screen_distance_mm':630}
        self.assertIsNone(summarize_e1_analysis(rows)[0]['wilcoxon'])

    def test_intentional_activations_do_not_become_a_zero_spontaneous_rate(self):
        rows=self.rows()
        rows.append({'participant_code':'DEMO','cohort':'pilot','root_session_id':'root','condition_id':'c1',
                     'engine':'mediapipe_ridge_calibrated','phase':'observation','attempted':True,
                     'exclusion_reasons':'observation_not_spontaneous_or_unreviewed',
                     'unintended_per_min':None,'activations':5,'observation_s':30})
        value=summarize_e1_analysis(rows)[0]['engines']['mediapipe_ridge_calibrated']
        self.assertEqual(value['i4_observations_excluded'],1)
        self.assertIsNone(value['i4_unintended_per_min'])


if __name__=='__main__':
    unittest.main()
