import requests
import time

# Create a new task
print('Testing task creation...')
resp = requests.post('http://127.0.0.1:8000/tasks', json={'task': 'Read main.py and tell me what it does', 'provider': 'local'})
print('Create:', resp.status_code, resp.json())
task_id = resp.json()['id']

# Start task
print('Starting task...')
resp = requests.post('http://127.0.0.1:8000/tasks/{}/start'.format(task_id))
print('Start:', resp.status_code, resp.json())

# Poll with more detail
print('Polling for completion...')
for i in range(30):
    time.sleep(2)
    resp = requests.get('http://127.0.0.1:8000/tasks/{}'.format(task_id))
    data = resp.json()
    print('Poll {}: status={}, logs={}'.format(i+1, data['status'], len(data['logs']) if data['logs'] else 0))
    if data['status'] in ['completed', 'failed', 'cancelled']:
        print('Result:', data['result'][:300] if data['result'] else None)
        if data['logs']:
            for log in data['logs']:
                print('  Log:', log)
        break