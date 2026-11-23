"""Synthetic, non-identifiable fixtures for validated cross-format import.

Passing these tests is not evidence that every vendor's native export is supported.
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app
from device_imports import normalize_glucose, normalize_pump, ImportProblem

CLIENT=TestClient(app)
ROOT=Path(__file__).resolve().parents[1]
DATE='2026-11-15'


def sensor_rows():
    return pd.DataFrame({'Timestamp':[f'{DATE} 08:00:00',f'{DATE} 08:05:00',f'{DATE} 09:00:00'],
                         'Glucose (mg/dL)':[110,120,130]})


def upload_sensor(name,contents,device='dexcomg7'):
    return CLIENT.post('/api/analyze',data={'mode':'libre','sensor_device':device},
                       files={'libre_file':(name,contents,'application/octet-stream')})


def test_old_libreview_file_still_analyzes():
    r=upload_sensor('libre.csv',(ROOT/'samples/example_libreview.csv').read_bytes(),'libre2')
    assert r.status_code==200, r.text
    assert r.json()['meal_timeline']['hourly_display'] and len(r.json()['meal_timeline']['hourly_display'])==24


def test_dexcom_clarity_csv_egv_filters_other_events():
    csv_data=(
        'Index,Timestamp (YYYY-MM-DDThh:mm:ss),Event Type,Glucose Value (mg/dL)\n'
        '1,2026-11-15T08:00:00,EGV,113\n'
        '2,2026-11-15T08:05:00,EGV,125\n'
        '3,2026-11-15T08:10:00,Calibration,150\n'
        '4,2026-11-15T09:00:00,EGV,130\n').encode()
    r=upload_sensor('clarity.csv',csv_data)
    assert r.status_code==200,r.text
    assert r.json()['libre']['summary']['readings']==3


def test_tidepool_json_cbg_ignores_smbg():
    payload=json.dumps([{'type':'cbg','time':f'{DATE}T{t}','value':n,'units':'mg/dL'}
                        for t,n in [('08:00:00',110),('08:10:00',120),('09:00:00',115)]]+
                       [{'type':'smbg','time':f'{DATE}T09:05:00','value':400,'units':'mg/dL'}]).encode()
    response=upload_sensor('tidepool.json',payload,'guardian4')
    assert response.status_code==200,response.text
    assert response.json()['libre']['summary']['readings']==3


def test_xlsx_sensor_worksheet_with_header():
    buf=io.BytesIO()
    sensor_rows().to_excel(buf,index=False,sheet_name='Glucose')
    response=upload_sensor('sensor.xlsx',buf.getvalue(),'eversense')
    assert response.status_code==200,response.text
    assert response.json()['libre']['summary']['readings']==3


def test_word_table_with_raw_sensor_rows():
    from docx import Document
    doc=Document(); tab=doc.add_table(rows=1,cols=2)
    tab.rows[0].cells[0].text='Timestamp';tab.rows[0].cells[1].text='Glucose (mg/dL)'
    for stamp,val in [('08:00',125),('08:10',135),('09:00',145)]:
        cells=tab.add_row().cells;cells[0].text=f'{DATE} {stamp}:00';cells[1].text=str(val)
    buf=io.BytesIO();doc.save(buf)
    response=upload_sensor('glucose.docx',buf.getvalue())
    assert response.status_code==200,response.text
    assert response.json()['libre']['summary']['readings']==3


def test_pdf_with_extractable_data_table():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate,Table,TableStyle
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=letter)
    table=Table([['Timestamp','Glucose (mg/dL)']]+[[f'{DATE} {t}:00',v] for t,v in [('08:00','101'),('08:10','109'),('09:00','127')]])
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),1,colors.black)]))
    doc.build([table])
    response=upload_sensor('readings.pdf',buf.getvalue())
    assert response.status_code==200,response.text
    assert response.json()['libre']['summary']['readings']==3


def test_generic_pump_basals_can_be_described_but_no_simulated_doses():
    sensor=sensor_rows().to_csv(index=False).encode()
    pump=('Date,Time,Basal Rate (U/h)\n'
          '2026/11/15,00:00:00,0.55\n'
          '2026/11/15,08:00:00,0.75\n'
          '2026/11/15,19:00:00,0.65\n').encode()
    response=CLIENT.post('/api/analyze',data={'mode':'both','sensor_device':'dexcomg7','pump_device':'tslim'},
        files={'libre_file':('sensor.csv',sensor,'text/csv'),'pump_file':('tandem.csv',pump,'text/csv')})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['pattern']['status']=='generic_basal_only'
    assert body['pattern']['segments']==[]
    assert body['pattern']['segments_changed']==0
    assert 'No basal schedule or dose-change simulation' in body['report']


def test_reject_pump_bolus_records_as_basal():
    data=('Timestamp,Bolus Units\n2026-11-15 08:00,3.0\n2026-11-15 12:00,4.0\n').encode()
    with pytest.raises(ImportProblem,match='No usable timestamped basal-rate'):
        normalize_pump(io.BytesIO(data),'pump.csv','omnipod5')


def test_reject_ambiguous_units_and_missing_raw_data():
    bad=b'Timestamp,Glucose\n2026-11-15 08:00,105\n2026-11-15 08:05,120\n'
    response=upload_sensor('sensor.csv',bad)
    assert response.status_code==422
    assert 'units' in response.json()['error'].lower()
    response=upload_sensor('sensor.pdf',b'not a real pdf')
    assert response.status_code==422
    assert 'PDF' in response.json()['error']


def test_disallows_unsupported_extension_even_if_content_is_csv():
    response=upload_sensor('glucose.exe',sensor_rows().to_csv(index=False).encode())
    assert response.status_code==422


def test_all_steps_require_explicit_selection_and_brighten():
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    assert 'id="sensorStep"' in html and 'id="pumpStep"' in html and 'id="timeStep"' in html
    assert 'id="clockSection" disabled' in html
    assert 'name="pumpChoice" value="no-pump" checked' not in html
    assert 'name="clockChoice" value="24" checked' not in html
    assert 'button.disabled=!selectedExportsSupported()' in html
    assert 'stepState==="completed"?"✓"' in html
