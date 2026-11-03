"""Local study analysis: manifest -> tables, figures and a standalone HTML report."""
import argparse
import csv
import hashlib
import html
import json
import statistics
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from research_stats import satisfaction
from study_analysis import (file_hash, load_e1, load_e2, pseudonym, read_json,
                            summarize_e1_analysis, summarize_e2)


def template():
    return {'schema_version':1,'dataset_label':'Completar etiqueta del conjunto','e2_exports':[],'e1_sessions':[],
            'questionnaires_csv':None,'text_evaluation':None,
            'randomizations':[], 'e1_reference_condition':'c1'}


def write_json(path, value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def write_csv(path, rows):
    if not rows:
        rows = [{'status':'no_data'}]
    fields = list(dict.fromkeys(k for row in rows for k in row if not k.startswith('_')))
    with Path(path).open('x',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            safe = {k: ("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()}
            writer.writerow(safe)


def questionnaire_rows(path):
    if path is None:
        return []
    result, seen = [], set()
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            code,assessment = pseudonym(row['participant_code']),pseudonym(row['assessment_id'])
            cohort = row['cohort']
            if cohort not in {'pilot','target'} or not row['form_version'].strip() or (code,cohort,assessment) in seen:
                raise ValueError('Invalid or duplicate questionnaire assessment')
            seen.add((code,cohort,assessment))
            def values(prefix,n):
                return [int(row.get(f'{prefix}{i}','').strip()) if row.get(f'{prefix}{i}','').strip() else None for i in range(1,n+1)]
            result.append({'participant_code':code,'cohort':cohort,'assessment_id':assessment,
                           'form_version':row['form_version'],**satisfaction(values('SUS',10),values('QUEST',12))})
    return result


def questionnaire_template(path):
    fields = ['participant_code','cohort','assessment_id','form_version']+[f'SUS{i}' for i in range(1,11)]+[f'QUEST{i}' for i in range(1,13)]
    with Path(path).open('x',encoding='utf-8-sig',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(fields)


def plot_results(folder, e2, e1):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype':'none','font.size':10})
    figures = []
    groups = defaultdict(list)
    for row in e2:
        groups[(row['participant_code'],row['cohort'],row['prediction_policy'],row['protocol_session'],row['session_id'][:8])].append(row)
    for key,rows in groups.items():
        rows.sort(key=lambda r:(r['session_id'],r['order'] or 0))
        fig,ax = plt.subplots(figsize=(9,4.5),layout='constrained')
        for label,color in [('without_prediction','#4b5563'),('with_prediction','#0369a1')]:
            values = [(i+1,r) for i,r in enumerate(rows) if r['condition']==label and r['duration_s'] is not None]
            ax.plot([i for i,r in values],[r['duration_s'] for i,r in values],marker='o',color=color,
                    label='Sin predicción' if label=='without_prediction' else 'Con predicción')
        excluded = [(i+1,r['duration_s']) for i,r in enumerate(rows) if not r['analysis_eligible'] and r['duration_s'] is not None]
        if excluded:
            ax.scatter(*zip(*excluded),marker='x',s=90,color='#b91c1c',label='Excluido del análisis principal')
        ax.set(xlabel='Ensayo observado (orden dentro de sesión)',ylabel='Tiempo por mensaje (s)',
               title=' / '.join(map(str,key)))
        ax.legend(loc='best')
        ax.grid(alpha=.2)
        name=f'e2_{len(figures)+1}.png'
        fig.savefig(folder/name,dpi=160)
        plt.close(fig)
        figures.append(name)
    grouped = defaultdict(list)
    for row in e1:
        if row['phase']=='angular' and row['attempted'] and not row['exclusion_reasons']:
            grouped[(row['participant_code'],row['cohort'],row['root_session_id'],row['condition_id'])].append(row)
    for key,rows in grouped.items():
        targets = sorted({str(r['target_id']) for r in rows})
        fig,ax = plt.subplots(figsize=(9,4.5),layout='constrained')
        for engine,color in [('gazecnn_generic','#4b5563'),('mediapipe_ridge_calibrated','#0369a1')]:
            values = [statistics.mean(r['angular_mean_screen_deg'] for r in rows if str(r['target_id'])==target and r['engine']==engine)
                      if any(str(r['target_id'])==target and r['engine']==engine for r in rows) else float('nan') for target in targets]
            ax.plot(targets,values,marker='o',color=color,label=engine)
        ax.set(xlabel='Objetivo',ylabel='Error angular operativo medio (°)',title=f'{key[0]} / {key[1]} / {key[3]}')
        ax.legend()
        ax.grid(alpha=.2)
        name=f'e1_{len(figures)+1}.png'
        fig.savefig(folder/name,dpi=160)
        plt.close(fig)
        figures.append(name)
    return figures


def render_html(folder, result, figures):
    def fmt(value):
        return '—' if value is None else f'{value:.3f}' if isinstance(value,float) else str(value)
    def table(headers,rows):
        return '<table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join('<td>'+html.escape(fmt(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>' if rows else '<p>No hay datos disponibles para este apartado.</p>'
    body = '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>InteractorGate — '+html.escape(result['scope']['dataset_label'])+'</title>'
    body += '<style>body{max-width:1100px;margin:36px auto;padding:0 20px;font:16px system-ui;color:#17202a}pre{white-space:pre-wrap;background:#f1f5f9;padding:18px;border-radius:8px}img{width:100%;height:auto}h1,h2{color:#164e63}.notice{background:#fff7ed;padding:18px}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}th,td{border-bottom:1px solid #cbd5e1;padding:10px;text-align:left}th{background:#e0f2fe}details{margin:24px 0}</style>'
    body += '</head><body><h1>Análisis de InteractorGate</h1><p class="notice">El análisis conserva prácticas, interrupciones y exclusiones. Los datos de piloto no demuestran eficacia en participantes. Un valor ausente no se sustituye por cero.</p>'
    body += '<p><strong>'+html.escape(result['scope']['dataset_label'])+'</strong></p>'
    body += '<h2>E2: composición de mensajes</h2><p>Solo los ensayos elegibles entran en medianas, NAP y latencia principal. CPM incluye espacios; KSR usa el número de caracteres objetivo como referencia literal.</p>'
    body += table(['Código','Grupo','Regla','Elegibles/total','Mediana sin (s)','Mediana con (s)','NAP tiempo','p95 principal (ms)','p95 observado incl. práctica (ms)'],[
        [r['participant_code'],r['cohort'],r['prediction_policy'],f"{r['eligible_trials']}/{r['total_trials']}",r['without']['median_duration_s'],r['with']['median_duration_s'],r['nap_duration_lower_better'],r['latency_p95_primary_shown_ms'],r['latency_p95_all_observed_shown_ms']] for r in result['e2']])
    body += table(['Código','Condición','n','Mediana selecciones','Mediana CPM','Mediana KSR','Aceptadas/presentación'],[
        [r['participant_code'],label,v['n'],v['median_composition_selections'],v['median_characters_per_minute'],v['median_ksr_literal_baseline'],v['acceptance_per_presentation']]
        for r in result['e2'] for label,v in [('Sin predicción',r['without']),('Con predicción',r['with'])]])
    body += '<p>La prueba de aleatorización requiere un espacio de asignación documentado. Las listas y los bloques actuales no permiten permutar libremente mensajes.</p>'
    body += table(['Código','Motivos de exclusión (un ensayo puede tener varios)'],[
        [r['participant_code'],'; '.join(f'{k}: {v}' for k,v in r['exclusions'].items()) or 'Ninguno'] for r in result['e2']])
    body += table(['Código','p de aleatorización','Asignaciones verificables aportadas'],[
        [r['participant_code'],r['randomization']['p_two_sided'] if r['randomization'] else None,r['randomization']['allocations'] if r['randomization'] else 0] for r in result['e2']])
    body += '<h2>E1: seguimiento ocular</h2><p>Los grados son operativos en pantalla, no el error nativo del modelo CNN. Completar el registro no acredita precisión suficiente.</p>'
    body += table(['Código','Motor','Objetivos medidos','Media (°)','I-2 aciertos/intentos','I-3 errores/confirmadas','Sin selección'],[
        [r['participant_code'],engine,v['angular_targets_measured'],v['angular_mean_of_targets_deg'],f"{v['i2_correct']}/{v['i2_attempted']}",f"{v['i3_wrong']}/{v['i3_confirmed']}",v['closed_without_selection']]
        for r in result['e1'] for engine,v in r['engines'].items()])
    body += table(['Código','Pares disponibles','p de Wilcoxon','Alcance'],[
        [r['participant_code'],r['paired_targets'],r['wilcoxon']['p_two_sided'] if r['wilcoxon'] else None,
         'Exploratorio; revisar supuestos' if r['wilcoxon'] else 'No calculado: parejas o geometrías incompatibles'] for r in result['e1']])
    body += table(['Código','Motor','Observaciones I-4 válidas','Observaciones excluidas','No intencionadas/min'],[
        [r['participant_code'],engine,v['i4_observations_eligible'],v['i4_observations_excluded'],v['i4_unintended_per_min']]
        for r in result['e1'] for engine,v in r['engines'].items()])
    body += '<h2>Cuestionarios</h2><p>SUS se expresa en puntos de 0 a 100, no en porcentaje. QUEST usa medias de respuestas válidas de 1 a 5; se conserva el número de respuestas.</p>'
    body += table(['Código','Grupo','SUS','Ítems SUS','QUEST dispositivo','QUEST servicios','QUEST total','Ítems QUEST'],[
        [r['participant_code'],r['cohort'],r['sus_score'],r['sus_valid_items'],r['quest_device_mean'],r['quest_services_mean'],r['quest_total_mean'],r['quest_valid_items']] for r in result['questionnaires']])
    body += '<h2>Predicción textual</h2>'
    text=result['text_evaluation']
    if text:
        body += '<p>Evaluación piloto retrospectiva. Las palabras fuera del vocabulario cuentan como errores en top-1/top-3 sobre palabras. La perplejidad incluye los símbolos de fin de frase y desconocida.</p>'
        body += table(['Partición','Modelo','Palabras','Fuera de vocabulario','Top-1 palabras','Top-3 palabras','Perplejidad LM'],[
            [part,model,v['word_positions'],v['word_oov'],v['word_top1'],v['word_top3'],v['perplexity']]
            for part in ('validation','test') for model,v in text['metrics'][part].items()])
    else:
        body += '<p>No se aportó una evaluación textual.</p>'
    body += '<h2>Figuras por sesión y objetivos</h2>'+''.join(f'<img src="{html.escape(name)}" alt="Gráfico de resultados">' for name in figures)
    body += '<h2>Tablas exportadas</h2><p><a href="e2_trials.csv">Ensayos E2</a> · <a href="e1_trials.csv">Ensayos E1</a> · <a href="questionnaires.csv">Cuestionarios</a> · <a href="analysis.json">Resultados JSON</a></p></html>'
    body = body.replace('</html>','<details><summary>Detalle de exclusiones, supuestos y trazabilidad</summary><pre>'+html.escape(json.dumps(result,ensure_ascii=False,indent=2))+'</pre></details></body></html>')
    (folder/'report.html').write_text(body,encoding='utf-8')


def analyze(manifest_path, output):
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    if manifest['schema_version'] != 1:
        raise ValueError('Unsupported analysis manifest')
    inputs = [{'name':path.name,'sha256':file_hash(path)}]
    def resolve(value):
        p = Path(value)
        return p if p.is_absolute() else path.parent/p
    e2_entries = [{**entry,'path':resolve(entry['path'])} for entry in manifest['e2_exports']]
    e1_entries = [{**entry,'path':resolve(entry['path'])} for entry in manifest['e1_sessions']]
    for entry in e2_entries:
        inputs.append({'name':entry['path'].name,'sha256':file_hash(entry['path'])})
    for entry in e1_entries:
        for name in ('session.json','events.jsonl','report.json'):
            source = entry['path']/name
            if source.exists():
                inputs.append({'name':entry['path'].name+'/'+name,'sha256':file_hash(source)})
    e2,diagnostics = load_e2(e2_entries)
    e1 = load_e1(e1_entries)
    questionnaire_file = resolve(manifest['questionnaires_csv']) if manifest.get('questionnaires_csv') else None
    questionnaires = questionnaire_rows(questionnaire_file)
    if questionnaire_file:
        inputs.append({'name':questionnaire_file.name,'sha256':file_hash(questionnaire_file)})
    text = None
    if manifest.get('text_evaluation'):
        source = resolve(manifest['text_evaluation'])
        text = read_json(source)
        inputs.append({'name':source.name,'sha256':file_hash(source)})
        text = {k:text[k] for k in ('scope','split_counts','vocabulary_size','oov','metrics','best_epoch','independent_validation')}
    result = {'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),
              'scope':{'cohorts':sorted({r['cohort'] for r in e2+e1+questionnaires}),
                       'dataset_label':str(manifest.get('dataset_label','Sin etiqueta')),
                       'e2_primary_trials':sum(r['analysis_eligible'] for r in e2),
                       'e2_confirmatory_claims':False,
                       'warnings':['Primary E2 excludes practice, incomplete/incorrect/inconsistent trials and unknown policy.',
                                   'Current E2 list assignment and alternating five-message blocks require a verified randomization space.',
                                   'E1 screen-ray errors are operational; geometry/version mismatches withhold paired inference.',
                                   'Intentional or unreviewed activations in observation do not validate spontaneous I-4.',
                                   'No participant satisfaction is inferred without questionnaire responses.']},
              'e2':summarize_e2(e2,manifest.get('randomizations')),
              'e2_diagnostics':diagnostics,
              'e1':summarize_e1_analysis(e1,manifest.get('e1_reference_condition','c1')),
              'questionnaires':questionnaires,'text_evaluation':text,'inputs':inputs,
              'analysis_code_sha256':{'frozen_executable':file_hash(sys.executable)} if getattr(sys,'frozen',False) else
                                    {name:file_hash(Path(__file__).parent/name) for name in
                                      ('study_analysis.py','research_stats.py','analyze_study.py','e1_protocol.py')}}
    folder = Path(output)/str(uuid.uuid4())
    folder.mkdir(parents=True,exist_ok=False)
    write_csv(folder/'e2_trials.csv',e2)
    write_csv(folder/'e1_trials.csv',e1)
    write_csv(folder/'questionnaires.csv',questionnaires)
    figures = plot_results(folder,e2,e1)
    result['software']={'python':sys.version,'matplotlib':sys.modules['matplotlib'].__version__}
    write_json(folder/'analysis.json',result)
    render_html(folder,result,figures)
    print(json.dumps({'folder':str(folder),'e2_trials':len(e2),'e1_trials':len(e1),'questionnaires':len(questionnaires),'figures':len(figures)}))
    return folder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--init-manifest',type=Path)
    parser.add_argument('--init-questionnaires',type=Path)
    args=parser.parse_args(argv)
    if args.init_manifest:
        write_json(args.init_manifest,template())
        return
    if args.init_questionnaires:
        questionnaire_template(args.init_questionnaires)
        return
    if not args.manifest:
        parser.error('Provide --manifest FILE')
    if args.output is None:
        from bench_precision import documents_folder
        args.output=documents_folder()/'InteractorGate'/'Analysis'
    return analyze(args.manifest,args.output)


if __name__=='__main__':
    main()
