"""Regression tests for historical LibreView and MiniMed CareLink raw CSV exports.

All fixtures are synthetic; no patient information is included in the package.
"""
from pathlib import Path
import io
import sys
import csv
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app
from device_imports import normalize_glucose, normalize_pump, ImportProblem

CLIENT = TestClient(app)


def old_libreview_with_metadata():
    return (
        'Export Date,Start Date,End Date,Device,Glucose Units\n'
        '2026-11-17,2026-11-01,2026-11-17,Libre Reader,mg/dL\n'
        'Device Timestamp,Record Type,Historic Glucose (mg/dL),Scan Glucose (mg/dL)\n'
        '15/11/2026 07:00:00,0,110,\n'
        '15/11/2026 07:05:00,0,114,\n'
        '15/11/2026 08:00:00,1,,115\n'
        '16/11/2026 12:00:00,0,128,\n'
        '16/11/2026 13:00:00,0,135,\n'
    ).encode()


def old_carelink_sparse_event_rows():
    import io
    stream=io.StringIO()
    writer=csv.writer(stream)
    writer.writerow(['Last Name','First Name','Patient ID','System ID','Start Date','End Date','Device','Pump Model'])
    writer.writerow(['Test','Patient','','','2026-11-01','2026-11-17','Serial Number','MiniMed 640G'])
    writer.writerow(['Patient DOB','','','','','','CGM','','Sensor Firmware Version'])
    writer.writerow([])
    writer.writerow([])
    writer.writerow(['-------','MiniMed 640G','Pump','DEIDENTIFIED','-------'])
    writer.writerow(['Index','Date','Time','New Device Time','BG Reading (mg/dL)',
                     'Linked BG Meter ID','Basal Rate (U/h)','Bolus Type','Bolus Volume Delivered (U)',
                     'Sensor Glucose (mg/dL)','Other Events'])
    # 30 events, but just four dated rate rows: the majority of CareLink
    # events legitimately have no basal rate value (not 0 U/h).
    times=['00:00:00','07:00:00','13:00:00','19:00:00']
    for i in range(30):
        rate=['0.75','0.80','0.85','0.90'][i//8] if i in (0,8,16,24) else ''
        writer.writerow([i,'2026/11/16',times[i//8], '', '', '', rate,
                         'Normal' if not rate else '', '1.2' if not rate else '', '', ''])
    return stream.getvalue().encode('utf-8')


def test_old_libreview_metadata_dates_do_not_hide_record_type_header():
    raw,description=normalize_glucose(io.BytesIO(old_libreview_with_metadata()),'libreview.csv','libre2')
    rows=list(csv.DictReader(io.StringIO(raw.decode())))
    assert len(rows)==4
    assert rows[0]['Historic Glucose (mg/dL)']=='110'
    assert 'mg/dL' in description


def test_carelink_metadata_dates_and_sparse_basal_events_are_accepted():
    raw,description,medtronic=normalize_pump(io.BytesIO(old_carelink_sparse_event_rows()),
                                              'minimed.csv','minimed600')
    rows=list(csv.DictReader(io.StringIO(raw.decode())))
    assert medtronic is True
    assert len(rows)==4
    assert rows[0]['Basal Rate (U/h)']=='0.75'
    assert all(float(r['Basal Rate (U/h)'])>0 for r in rows)


def test_original_libreview_and_carelink_can_be_uploaded_together():
    response=CLIENT.post('/api/analyze',data={
        'mode':'both','sensor_device':'libre2','pump_device':'minimed600'},
        files={
            'libre_file':('libre.csv',old_libreview_with_metadata(),'text/csv'),
            'pump_file':('minimed.csv',old_carelink_sparse_event_rows(),'text/csv')})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['libre']['summary']['readings']==4
    assert result['import_info']['pump']=='minimed600'


def test_administrative_dates_alone_are_not_glucose_measurements():
    meta=('Start Date,End Date,Device\n2026-11-01,2026-11-17,Libre\n').encode()
    with pytest.raises(ImportProblem,match='No recognizable raw sensor-glucose'):
        normalize_glucose(io.BytesIO(meta),'export.csv','libre2')
