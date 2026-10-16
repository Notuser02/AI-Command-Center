import requests
import time

# Test create task
print('Testing task creation...')
resp = requests.post('http://127.0.0.1:8000/tasks', json={'task': 'List files in the project', 'provider': 'local'})
print('Create:', resp.status_code, resp.json())

task_id = resp.json()['id']

# Test list tasks
print('Testing list tasks...')
resp = requests.get('http://127.0.0.1:8000/tasks')
print('List:', resp.status_code, resp.json())

# Test get task
print('Testing get task', task_id)
resp = requests.get('http://127.0.0.1:8000/tasks/{}'.format(task_id))
print('Get:', resp.status_code, resp.json())

# Test start task
print('Testing start task', task_id)
resp = requests.post('http://127.0.0.1:8000/tasks/{}/start'.format(task_id))
print('Start:', resp.status_code, resp.json())

# Poll for completion
print('Polling for completion...')
for i in range(30):
    time.sleep(2)
    resp = requests.get('http://127.0.0.1:8000/tasks/{}'.format(task_id))
    data = resp.json()
    print('Poll {}: status={}'.format(i+1, data['status']))
    if data['status'] in ['completed', 'failed', 'cancelled']:
        print('Result:', data['result'][:200] if data['result'] else None)
        print('Logs:', len(data['logs']) if data['logs'] else 0, 'entries')
        break