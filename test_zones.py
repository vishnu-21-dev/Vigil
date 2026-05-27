import requests

BASE = 'http://127.0.0.1:8000'

# 1. List seeded zones
zones = requests.get(f'{BASE}/zones/').json()
print('1. Seeded zones:', len(zones))
for z in zones:
    print(f'   {z["name"]}: {z["subnet"]}')

# 2. Create a custom zone
new_zone = requests.post(f'{BASE}/zones/', json={
    'name': 'DMZ',
    'description': 'Demilitarized zone',
    'subnet': '10.0.50.0/24',
    'ip_range_start': '10.0.50.1',
    'ip_range_end': '10.0.50.254'
}).json()
print('2. Created zone:', new_zone['name'], new_zone['id'])

# 3. IP lookup — should match Production Floor
lookup = requests.get(f'{BASE}/zones/lookup/10.0.10.25').json()
print('3. IP lookup 10.0.10.25:', lookup.get('name', lookup))

# 4. IP lookup — should match new DMZ zone
lookup2 = requests.get(f'{BASE}/zones/lookup/10.0.50.100').json()
print('4. IP lookup 10.0.50.100:', lookup2.get('name', lookup2))

# 5. IP lookup — no match
lookup3 = requests.get(f'{BASE}/zones/lookup/192.168.1.1').json()
print('5. IP lookup 192.168.1.1:', lookup3)

# 6. Create device — auto zone assign
device = requests.post(f'{BASE}/devices/', json={
    'name': 'Auto Zone Sensor',
    'ip_address': '10.0.30.55',
    'zone': 'Unknown'
}).json()
print('6. Device zone (should be Warehouse):', device['zone'])

# 7. Try deleting a zone with devices
delete_resp = requests.delete(f'{BASE}/zones/{zones[0]["id"]}').json()
print('7. Delete zone with devices:', delete_resp)

# 8. Update a zone
updated = requests.put(f'{BASE}/zones/{new_zone["id"]}', json={
    'description': 'Updated DMZ description'
}).json()
print('8. Updated zone description:', updated['description'])