import json
import subprocess
import os

def get_git_modified_files():
    result = subprocess.run(['git', 'ls-files', '-m', 'backend/helix/scoring/instruments/definitions/*.json'], capture_output=True, text=True)
    return result.stdout.strip().split('\n')

def get_head_file(filepath):
    result = subprocess.run(['git', 'show', f'HEAD:{filepath}'], capture_output=True, text=True)
    if not result.stdout: return {}
    return json.loads(result.stdout)

def get_current_file(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return {}

files = get_git_modified_files()
report = []

for f in files:
    if not f: continue
    head = get_head_file(f)
    curr = get_current_file(f)
    
    fname = os.path.basename(f)
    file_report = {"file": fname, "changes": []}
    
    # Check bands
    head_bands = head.get('scoring', {}).get('bands')
    curr_bands = curr.get('scoring', {}).get('bands')
    if head_bands != curr_bands:
        file_report["changes"].append({
            "field": "scoring.bands",
            "old": head_bands,
            "new": curr_bands
        })
            
    # Check band_descriptions
    head_desc = head.get('band_descriptions')
    curr_desc = curr.get('band_descriptions')
    if head_desc != curr_desc:
        file_report["changes"].append({
            "field": "band_descriptions",
            "old": head_desc,
            "new": curr_desc
        })

    # Check for new root fields
    head_keys = set(head.keys())
    curr_keys = set(curr.keys())
    new_keys = curr_keys - head_keys
    if new_keys:
        file_report["changes"].append({
            "field": "root_keys",
            "added": list(new_keys)
        })
        
    # Check scoring subscales
    head_subs = head.get('scoring', {}).get('subscales')
    curr_subs = curr.get('scoring', {}).get('subscales')
    if head_subs != curr_subs:
        file_report["changes"].append({
            "field": "scoring.subscales",
            "changed": True
        })

    if file_report["changes"]:
        report.append(file_report)

print(json.dumps(report, indent=2))
