"""Generate repository-local profile cards from GitHub data; no dependencies."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
THEMES = {
    'dark': {'bg': '#0d1117', 'ink': '#e6edf3', 'muted': '#8e9cab', 'line': '#273441', 'accent': '#64dfca'},
    'light': {'bg': '#ffffff', 'ink': '#172b3a', 'muted': '#586b7a', 'line': '#d2dce3', 'accent': '#087f72'},
}
COLORS = ['#64dfca', '#6d9eff', '#c69bff', '#f0be76', '#f28eae', '#91acbc']

def api(path, token, payload=None):
    headers = {'User-Agent': 'khalifehbasiri-profile', 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request('https://api.github.com/' + path, headers=headers,
                  data=json.dumps(payload).encode() if payload else None)
    with urlopen(req, timeout=40) as response:
        return json.load(response)

def list_repos(endpoint, token):
    repos, page = [], 1
    while True:
        batch = api(f'{endpoint}&per_page=100&page={page}', token)
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos

def fetch(username, token, include_private=False, activity_only=False, languages_only=False):
    data = {'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d')}
    if include_private:
        account = api('user', token)
        if account['login'].lower() != username.lower():
            raise RuntimeError('The private-repository token must belong to the profile owner.')
        repos = list_repos('user/repos?affiliation=owner&visibility=all', token)
        repos = [r for r in repos if not r['fork'] and r['owner']['login'].lower() == username.lower()]
    else:
        repos = list_repos(f'users/{username}/repos?type=owner', token)
        repos = [r for r in repos if not r['fork'] and not r['private']]
    if not activity_only:
        languages = Counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            for counts in pool.map(lambda r: api(f'repos/{r["full_name"]}/languages', token), repos):
                languages.update(counts)
        data.update({
            'languages': dict(languages.most_common()),
            'language_scope': 'public + private' if include_private else 'public',
            'language_repositories': len(repos),
            'included_private_repositories': sum(r['private'] for r in repos),
        })
    if languages_only:
        return data
    query = '''query($login:String!) { user(login:$login) { contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    } } }'''
    result = api('graphql', token, {'query': query, 'variables': {'login': username}})
    if result.get('errors'):
        raise RuntimeError('GitHub contribution query failed: ' + result['errors'][0]['message'])
    calendar = result['data']['user']['contributionsCollection']['contributionCalendar']
    days = sorted((d for w in calendar['weeks'] for d in w['contributionDays']), key=lambda d: d['date'])
    streak = longest = 0
    for day in days:
        streak = streak + 1 if day['contributionCount'] else 0
        longest = max(longest, streak)
    data.update({
        'contributions': calendar['totalContributions'],
        'active_days': sum(d['contributionCount'] > 0 for d in days),
        'longest_streak': longest, 'public_repos': sum(not r['private'] for r in repos),
    })
    return data

def svg_start(title, t):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="560" height="248" viewBox="0 0 560 248" role="img" aria-labelledby="title">
    <title id="title">{escape(title)}</title>
    <rect x="1" y="1" width="558" height="246" rx="14" fill="{t['bg']}" stroke="{t['line']}"/>
    <g font-family="Segoe UI,Arial,sans-serif">'''

def text(x, y, content, t, size=14, muted=False, weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{t["muted" if muted else "ink"]}">{escape(str(content))}</text>'

def stats_svg(data, t):
    s = svg_start('GitHub activity over the last year', t)
    s += text(28, 36, 'ACTIVITY / LAST YEAR', t, 12, True, 600)
    metrics = [(28, 96, data['contributions'], 'contributions'), (302, 96, data['active_days'], 'active days'),
               (28, 179, data['longest_streak'], 'longest streak · days'), (302, 179, data['public_repos'], 'public repos · non-forks')]
    for x, y, value, label in metrics:
        s += text(x, y, f'{value:,}', t, 38, weight=700)
        s += text(x, y + 25, label, t, 13, True)
    s += f'<path d="M 277 64 V 208 M 28 136 H 532" stroke="{t["line"]}"/>'
    s += text(28, 230, 'github.com/khalifehbasiri · updated ' + data['updated'], t, 10, True)
    return s + '</g></svg>'

def languages_svg(data, t):
    all_repos = data['language_scope'] == 'public + private'
    scope = 'public and private' if all_repos else 'public'
    s = svg_start(f'Language mix by bytes in owned {scope} non-fork repositories', t)
    heading = 'CODE MIX / PUBLIC + PRIVATE' if all_repos else 'CODE MIX / PUBLIC REPOS'
    s += text(28, 36, heading, t, 12, True, 600)
    pairs = list(data['languages'].items())
    total = sum(v for _, v in pairs)
    if not total:
        return s + text(28, 110, 'No language data available yet.', t) + '</g></svg>'
    shown = pairs[:5]
    if len(pairs) > 5:
        shown.append(('Other', sum(v for _, v in pairs[5:])))
    x = 28
    for i, (name, value) in enumerate(shown):
        width = value / total * 504
        s += f'<rect x="{x:.2f}" y="64" width="{width:.2f}" height="18" fill="{COLORS[i]}"/>'
        x += width
    for i, (name, value) in enumerate(shown):
        x, y = 28 + (i % 2) * 265, 119 + (i // 2) * 37
        s += f'<circle cx="{x + 5}" cy="{y - 5}" r="5" fill="{COLORS[i]}"/>'
        s += text(x + 20, y, name, t, 13, weight=600)
        s += text(x + 175, y, f'{value / total:.1%}', t, 12, True)
    s += text(28, 230, 'Code bytes, not proficiency · updated ' + data['updated'], t, 10, True)
    return s + '</g></svg>'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default='khalifehbasiri')
    parser.add_argument('--local-gh', action='store_true', help='Use existing GitHub CLI login locally.')
    parser.add_argument('--include-private', action='store_true', help='Include owned private repositories in language totals.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--activity-only', action='store_true', help='Update activity cards and preserve the language cards.')
    mode.add_argument('--languages-only', action='store_true', help='Update language cards and preserve the activity cards.')
    args = parser.parse_args()
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if args.local_gh:
        token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
    if not token:
        raise SystemExit('Set GH_TOKEN/GITHUB_TOKEN or use --local-gh. No token is saved to files.')
    data = fetch(args.username, token, args.include_private, args.activity_only, args.languages_only)
    assets = ROOT / 'assets'
    assets.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        if not args.languages_only:
            (assets / f'stats-{theme}.svg').write_text(stats_svg(data, t), encoding='utf-8')
        if not args.activity_only:
            (assets / f'languages-{theme}.svg').write_text(languages_svg(data, t), encoding='utf-8')
    print(json.dumps(data))

if __name__ == '__main__':
    main()
