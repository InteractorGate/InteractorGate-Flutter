"""Synthetic arithmetic oracle, not participant data or an efficacy experiment."""
import csv
import hashlib
import itertools
import json
import sys
import uuid
from pathlib import Path


def example(folder):
    folder = Path(folder)
    folder.mkdir(parents=True,exist_ok=False)
    def identity(label):
        return str(uuid.UUID(bytes=hashlib.sha256(label.encode()).digest()[:16],version=4))
    session = identity('manual-session')
    events = []
    def emit(kind,data=None):
        event={'event_id':identity(f'event-{len(events)}'),'session_id':session,'sequence':len(events)+1,
               'user_id':1,'participant_id':1,'schema_version':2,'event_type':kind,
               'timestamp':'2026-11-03T00:00:00+00:00'}
        if data is not None:
            event['data']=data
        events.append(event)
    emit('session_start')
    ids=[]
    for i,duration in enumerate((10,20,5,15)):
        condition='without_prediction' if i<2 else 'with_prediction'
        tid=identity(f'trial-{i}')
        ids.append(tid)
        common={'trial_id':tid,'study':'E2','target_phrase':'YO VOY','phrase_id':f'M{i+1}',
                'condition':condition,'practice':False,'block':1 if i<2 else 2,'order':i+1,
                'protocol_session':'s2','bank_version':'manual-v1','list':'B' if i<2 else 'A',
                'participant_number':1,'provisional':True}
        emit('trial_start',common)
        text=''
        for char in ('YO VOY' if i<2 else 'YO '):
            text+=char
            emit('selection',{**common,'action':'space' if char==' ' else 'letter',
                              'removed_characters':0,'inserted_text':char,'text_length':len(text)})
        if i>=2:
            request=identity(f'request-{i}')
            emit('suggestions',{**common,'action':'requested','request_id':request})
            emit('suggestions',{**common,'action':'shown','request_id':request,
                                'suggestions':['VOY'],'latency_ms':100 if i==2 else 300})
            emit('selection',{**common,'action':'suggestion','request_id':request,'suggestion_rank':1,
                              'removed_characters':1,'inserted_text':' VOY','text_length':6})
        emit('trial_end',{**common,'status':'completed','duration_ms':duration*1000,'final_text':'YO VOY'})
    emit('session_end')
    export={'export_version':1,'participant_code':'DEMO01','session_id':session,'count':len(events),'logs':events}
    (folder/'manual_export.json').write_text(json.dumps(export,indent=2),encoding='utf-8')
    fields=['participant_code','cohort','assessment_id','form_version']+[f'SUS{i}' for i in range(1,11)]+[f'QUEST{i}' for i in range(1,13)]
    with (folder/'manual_questionnaires.csv').open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        writer.writerow({'participant_code':'DEMO01','cohort':'pilot','assessment_id':'DEMO_Q1',
                         'form_version':'synthetic_arithmetic_only',
                         **{f'SUS{i}':4 if i%2 else 2 for i in range(1,11)},
                         **{f'QUEST{i}':4 if i<=8 else 3 for i in range(1,13)}})
    allocations=[]
    for positions in itertools.combinations(range(4),2):
        allocations.append([i in positions for i in range(4)])
    manifest={'schema_version':1,'dataset_label':'EJEMPLO SINTETICO — comprobacion aritmetica',
              'e2_exports':[{'path':'manual_export.json','cohort':'pilot','environment':'synthetic',
                             'prediction_policy':'next_words_v1'}],'e1_sessions':[],
              'questionnaires_csv':'manual_questionnaires.csv','text_evaluation':None,
              'randomizations':[{'participant_code':'DEMO01','cohort':'pilot','environment':'synthetic',
                                  'prediction_policy':'next_words_v1','bank_version':'manual-v1',
                                  'trial_ids':ids,'assignments':allocations}],
              'e1_reference_condition':'c1'}
    (folder/'manual_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    expected={'median_without_s':15,'median_with_s':10,'median_without_selections':6,
              'median_with_selections':4,'median_without_cpm':27,'median_with_cpm':48,
              'ksr_without':0,'ksr_with':1/3,'nap_time':.75,'nap_selections':1,
              'p95_ms':290,'randomization_p':2/3,'sus':75,'quest_device':4,
              'quest_services':3,'quest_total':11/3}
    (folder/'expected_manual.json').write_text(json.dumps(expected,indent=2),encoding='utf-8')
    return folder/'manual_manifest.json'


if __name__=='__main__':
    print(example(sys.argv[1]))
