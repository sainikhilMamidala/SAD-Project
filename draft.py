import subprocess
import os
import shutil
import pandas as pd
import json
import requests
import radon.complexity as radon_cc

GITHUB_TOKEN = 'GITHUB_TOKEN'  # Replace with your token or None
REPOS = [
    'https://github.com/psf/black', 
'https://github.com/PyCQA/pylint', 
'https://github.com/PyCQA/bandit',
'https://github.com/pycqa/flake8',
'https://github.com/joerick/cibuildwheel'
    # add more repositories as needed
]

def get_python_files(directory):
    py_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                py_files.append(os.path.join(root, file))
    return py_files

def check_for_tools(repo_path):
    configs = ['.sonar-project.properties', '.codeclimate.yml', 'tox.ini', 'ci.yml', 'github/workflows']
    used_tools = {}
    for conf in configs:
        if os.path.exists(os.path.join(repo_path, conf)):
            used_tools[conf] = True
    readme_path = os.path.join(repo_path, 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()
            if 'sonar' in content:
                used_tools['SonarQube'] = True
            if 'codeclimate' in content:
                used_tools['CodeClimate'] = True
            if 'bandit' in content:
                used_tools['Bandit'] = True
    return used_tools

def get_bug_issues_count(owner, repo, token=None):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'
    params = {
        'state': 'closed',
        'per_page': 100,
        'page': 1
    }
    bug_count = 0
    while True:
        r = requests.get(url, headers=headers, params=params)
        if r.status_code != 200:
            print(f"GitHub API error for {owner}/{repo}: {r.status_code}")
            break
        issues = r.json()
        bug_count += len(issues)
        if 'Link' in r.headers:
            if 'rel="next"' in r.headers['Link']:
                params['page'] += 1
            else:
                break
        else:
            break
    print(f"Bug issues in {owner}/{repo}: {bug_count}")
    return bug_count

def get_loc(repo_path):
    total_lines = 0
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith('.py'):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        total_lines += len(lines)
                except:
                    continue
    print(f"Total LOC in {repo_path}: {total_lines/1000:.2f} KLOC")
    return total_lines / 1000

def analyze_complexity(py_files):
    complexities = []
    for f in py_files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                code = file.read()
            cc_blocks = radon_cc.cc_visit(code)
            complexities.extend([b.complexity for b in cc_blocks])
        except Exception as e:
            print(f"Error analyzing {f}: {e}")
            continue
    if complexities:
        return sum(complexities) / len(complexities)
    return 0.0

def run_pylint(repo_path):
    try:
        r = subprocess.run(
            ['pylint', repo_path, '--output-format=json', '--exit-zero'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        if r.stdout.strip():
            reports = json.loads(r.stdout)
            return len(reports)
        return 0
    except:
        return None

def run_bandit(repo_path):
    try:
        r = subprocess.run(
            ['bandit', '-r', repo_path, '-f', 'json', '-q'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        report = json.loads(r.stdout) if r.stdout.strip() else {}
        return len(report.get('results', []))
    except:
        return None

rows = []

for repo_url in REPOS:
    repo_name = repo_url.rstrip('/').split('/')[-1]
    # Remove .git if present
    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]
    owner = repo_url.rstrip('/').split('/')[-2]
    repo_path = os.path.join(os.getcwd(), repo_name)

    # Remove previous clone if exists
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path, ignore_errors=True)
        print(f"Removed existing directory {repo_path}")

    print(f"\nCloning {repo_url} into {repo_path}...")
    try:
        subprocess.run(['git', 'clone', '--depth', '1', repo_url], check=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning {repo_name}: {e}")
        rows.append({'Repository': repo_name, 'Status': 'clone_failed'})
        continue

    # Debug: list contents after clone
    print(f"Contents of {repo_path}: {os.listdir(repo_path)}")

    # Check tools
    tools_used = check_for_tools(repo_path)

    # Bug issues count
    bug_issues = get_bug_issues_count(owner, repo_name, token=GITHUB_TOKEN)

    # Total LOC
    total_loc = get_loc(repo_path)
    # Calculate defect density
    defect_density = bug_issues / total_loc if total_loc else None

    # Find Python files
    py_files = get_python_files(repo_path)
    total_py_files = len(py_files)

    # Complexity
    avg_complexity = analyze_complexity(py_files)

    # Modules count
    module_count = total_py_files

    # Static analysis tools
    pylint_issues = run_pylint(repo_path)
    bandit_issues = run_bandit(repo_path)

    # Save row
    rows.append({
        'Repository': repo_name,
        'Status': 'ok',
        'Owner': owner,
        'Module_Count': total_py_files,
        'Avg_Complexity': round(avg_complexity, 2),
        'Pylint_Issues': pylint_issues,
        'Bandit_Issues': bandit_issues,
        'Bug_Issues': bug_issues,
        'Defect_Density': round(defect_density, 4) if defect_density is not None else None,
        'Tools_Detected': list(set(tools_used.keys()))
    })

    # Cleanup
    shutil.rmtree(repo_path, ignore_errors=True)
    print(f"Finished processing {repo_name}.")

# Save to CSV
df = pd.DataFrame(rows)
df.to_csv('python_repo_metrics.csv', index=False)
print("\nAnalysis complete. Results saved to 'python_repo_metrics.csv'.")