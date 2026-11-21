import urllib.request
import json
from datetime import datetime

# 1. Helper to login and get token
def get_token():
    url = "http://127.0.0.1:8000/api/auth/login/"
    data = {
        "username": "testuser_debug_urllib", # Created in previous step
        "password": "testpassword123"
    }
    json_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=json_data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            res_json = json.loads(response.read().decode('utf-8'))
            return res_json['access']
    except Exception as e:
        print(f"Login Failed: {e}")
        return None

# 2. Create Attendance Record
def create_attendance(token):
    url = "http://127.0.0.1:8000/api/attendance/"
    today = datetime.now().strftime('%Y-%m-%d')
    # Need to fetch user ID first usually, but for this test we might need to be admin or just user posting own attendance depending on permissions.
    # Actually ModelViewSet allows posting if not restricted.
    # But wait, we need 'user' field in payload if we are admin, or it might be auto-set. 
    # Let's check Serializer... it's __all__. So we need 'user' ID.
    
    # Quick hack: Assume user ID 3 from previous creation.
    data = {
        "user": 3,
        "date": today,
        "time_in": "09:00:00",
        "time_out": "18:00:00",
        "status": "PRESENT"
    }
    json_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=json_data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    })
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Create Attendance Status: {response.getcode()}")
            return True
    except urllib.error.HTTPError as e:
        # If it fails, maybe duplicate entry (unique together constraints?), ignore
        print(f"Create Attendance Failed (might be duplicate): {e}")
        return True
    except Exception as e:
        print(f"Create Error: {e}")
        return False

# 3. Verify Fetch with Date Filter
def verify_fetch(token):
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"http://127.0.0.1:8000/api/attendance/?date={today}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}'
    })
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            print(f"Fetched {len(data)} records for {today}")
            if len(data) > 0:
                print(f"First record username: {data[0].get('username')}")
                if 'username' in data[0] and 'time_in' in data[0]:
                    print("SUCCESS: Payload contains username and time_in")
                else:
                    print("FAILURE: Payload missing fields")
            else:
                 print("FAILURE: No records found")
    except Exception as e:
        print(f"Fetch Error: {e}")

token = get_token()
if token:
    create_attendance(token)
    verify_fetch(token)
