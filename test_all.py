import requests, pandas as pd

BASE = 'http://127.0.0.1:8000'

# 1. Health check
r = requests.get(f'{BASE}/health')
print('1. Health:', r.json())

# 2. List devices
devices = requests.get(f'{BASE}/devices/').json()
print('2. Devices:', len(devices), 'devices loaded')

# 3. Create a device manually
new_device = requests.post(f'{BASE}/devices/', json={
    'name': 'Test Sensor', 'ip_address': '10.0.99.1', 'zone': 'Test Zone'
}).json()
print('3. Created device:', new_device['id'])

# 4. Ingest benign traffic
df_benign = pd.read_csv('data/1.benign.csv', nrows=1)
benign_resp = requests.post(f'{BASE}/monitor/ingest', json={
    'device_id': new_device['id'],
    'features': df_benign.iloc[0].to_dict()
}).json()
print('4. Benign ingest:', benign_resp)

# 5. Ingest attack traffic
df_attack = pd.read_csv('data/1.mirai.ack.csv', nrows=1)
attack_resp = requests.post(f'{BASE}/monitor/ingest', json={
    'device_id': new_device['id'],
    'features': df_attack.iloc[0].to_dict()
}).json()
print('5. Attack ingest:', attack_resp)

# 6. Check alerts
alerts = requests.get(f'{BASE}/alerts/').json()
print('6. Alerts:', len(alerts), 'total')

# 7. Check quarantine requests
qr_list = requests.get(f'{BASE}/quarantine/').json()
print('7. Quarantine requests:', len(qr_list), 'total')

# 8. Approve quarantine
qr_id = attack_resp.get('quarantine_request_id')
if qr_id:
    approval = requests.post(f'{BASE}/quarantine/{qr_id}/approve', json={
        'approved_by': 'admin', 'notes': 'test approval'
    }).json()
    print('8. Quarantine approved:', approval['status'])
else:
    print('8. No quarantine_request_id found')

# 9. Check device status
device_check = requests.get(f'{BASE}/devices/{new_device["id"]}').json()
print('9. Device status after quarantine:', device_check['status'])

# 10. Generate incident report
alert_id = alerts[0]['id']
report = requests.post(f'{BASE}/reports/generate', json={
    'alert_id': alert_id,
    'additional_context': 'Detected during routine monitoring'
}).json()
print('10. Report title:', report.get('title'))
print('    Severity:', report.get('severity'))
print('    Summary:', report.get('summary'))