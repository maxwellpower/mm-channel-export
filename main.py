# Mattermost Channel Export

# Copyright (c) 2024 Maxwell Power
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom
# the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
# AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

VERSION = "1.0.5"

import requests
import os
import csv
import json
import logging
from datetime import datetime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from dotenv import load_dotenv
import urllib3
from collections import defaultdict
import re
import markdown

# Load environment variables
load_dotenv()

# Configuration
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
CHANNEL_ID = os.getenv('CHANNEL_ID')
START_DATE = os.getenv('START_DATE')
END_DATE = os.getenv('END_DATE')
FETCH_ALL = os.getenv('FETCH_ALL', 'False').lower() == 'true'
VERIFY_SSL = os.getenv('VERIFY_SSL', 'True').lower() == 'true'
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
HEADERS = {'Authorization': f'Bearer {API_TOKEN}'}

# Set up logging
log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("output/export.log"), logging.StreamHandler()])

# Suppress SSL warnings if VERIFY_SSL is False
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Session setup with retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))

# User cache
user_cache = {}
is_system_admin = False

def validate_config():
    if not API_TOKEN or not BASE_URL or not CHANNEL_ID:
        logging.error("ERROR: Missing essential configuration. Please set API_TOKEN, BASE_URL, and CHANNEL_ID.")
        exit(1)

def get_current_user():
    url = f'{BASE_URL}/users/me'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    user_info = response.json()
    return user_info

def check_system_admin():
    global is_system_admin
    current_user = get_current_user()
    roles = current_user.get('roles', '')
    is_system_admin = 'system_admin' in roles
    if is_system_admin:
        logging.info("User is a system admin. Fetching deleted posts is enabled.")
    else:
        logging.warning("User is not a system admin. Fetching deleted posts is disabled.")

def get_user(user_id):
    if user_id in user_cache:
        return user_cache[user_id]
    url = f'{BASE_URL}/users/{user_id}'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    user_info = response.json()
    user_cache[user_id] = user_info
    logging.debug(f"Retrieved user info: {user_info}")
    return user_info

def get_file_info(file_id):
    url = f'{BASE_URL}/files/{file_id}/info'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    file_info = response.json()
    logging.debug(f"Retrieved file info: {file_info}")
    return {
        'id': file_info.get('id'),
        'name': file_info.get('name'),
        'size': file_info.get('size'),
        'mime_type': file_info.get('mime_type'),
        'upload_time': datetime.fromtimestamp(file_info['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S') if file_info.get('create_at') else 'N/A',
        'uploader_id': file_info.get('user_id'),
        'download_url': f'{BASE_URL}/files/{file_id}'
    }

def get_channel_name(channel_id):
    url = f'{BASE_URL}/channels/{channel_id}'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    channel_info = response.json()
    logging.info("Successfully connected to API")
    logging.debug(f"Channel info: {channel_info}")
    return channel_info['display_name']

def get_reactions(post_id):
    url = f'{BASE_URL}/posts/{post_id}/reactions'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    reactions = response.json() or []
    logging.debug(f"Reactions for post {post_id}: {reactions}")
    
    reaction_details = defaultdict(list)
    for reaction in reactions:
        user_info = get_user(reaction['user_id'])
        reaction_details[reaction['emoji_name']].append(user_info['username'])
    
    return [{'emoji_name': emoji, 'users': users, 'count': len(users)} for emoji, users in reaction_details.items()]

def highlight_mentions(message):
    return re.sub(r'(@[a-zA-Z0-9_.-]+)', r'<span style="color: blue;">\1</span>', message)

def format_markdown(message):
    html = markdown.markdown(message, extensions=['fenced_code', 'tables'])
    return html

def get_posts(channel_id):
    all_posts = []
    page = 0
    per_page = 100

    while True:
        params = {'page': page, 'per_page': per_page}
        if is_system_admin:
            params['include_deleted'] = "true"  # Include deleted posts for system admins
        url = f'{BASE_URL}/channels/{channel_id}/posts'
        response = session.get(url, headers=HEADERS, params=params, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()
        posts = data.get('posts', {})
        if not posts:
            break
        all_posts.extend(posts.values())
        if not data.get('has_next', False):
            break
        page += 1

    sorted_posts = sorted(all_posts, key=lambda x: x['create_at'])
    return sorted_posts

def filter_posts_by_date(posts, start_date, end_date):
    start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000) if start_date else None
    end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000) if end_date else None
    filtered_posts = []
    
    for post in posts:
        post_timestamp = post['create_at']
        if (start_timestamp and post_timestamp < start_timestamp) or (end_timestamp and post_timestamp > end_timestamp):
            continue
        filtered_posts.append(post)
    
    return filtered_posts

def add_post(all_posts, post):
    post_details = {
        'id': post['id'],
        'message': post.get('message', ''),
        'user_id': post['user_id'],
        'create_at': post['create_at'],
        'edit_at': post.get('edit_at', 0),
        'delete_at': post.get('delete_at', 0),
        'root_id': post.get('root_id', ''),
        'parent_id': post.get('parent_id', ''),
        'files': [get_file_info(file_id) for file_id in post.get('file_ids', [])],
        'reactions': get_reactions(post['id']),
        'replies': []
    }
    if post_details['root_id']:
        if post_details['root_id'] in all_posts:
            all_posts[post_details['root_id']]['replies'].append(post_details)
        else:
            all_posts[post_details['root_id']] = {'replies': [post_details]}
    else:
        if post['id'] in all_posts:
            all_posts[post['id']].update(post_details)
        else:
            all_posts[post['id']] = post_details

def generate_html(posts, start_date, end_date, channel_name):
    date_range = "For all time" if FETCH_ALL else f"From {start_date} to {end_date}"

    if not posts:
        logging.info("No posts available to write to HTML.")
    
    html = f'''<html><head><title>Mattermost Channel Posts Export</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body>
<div class="container-flex">
    <div class="text-center my-4">
        <h1>Mattermost Channel Posts Export</h1>
        <h2>Posts in Channel {channel_name}</h2>
        <h3>{date_range}</h3>
    </div>
    <div class="table-responsive">
        <table class="table table-bordered table-hover">
            <thead><tr class="table-dark"><th>ID</th><th>Message</th><th>Posted By</th><th>Date</th><th>Edited</th><th>Deleted</th><th>Attachments</th><th>Reactions</th><th>Thread</th></tr></thead>
            <tbody>'''

    for post in posts:
        html += format_post(post, is_main=True)
        for reply in sorted(post.get('replies', []), key=lambda x: x['create_at']):
            html += format_post(reply, is_main=False)

    html += '</tbody></table></div></div></body></html>'
    output_path = os.path.join('output', channel_name)
    os.makedirs(output_path, exist_ok=True)
    with open(os.path.join(output_path, f'{channel_name}.html'), 'w') as f:
        f.write(html)

def format_post(post, is_main):
    style = "table-active" if is_main else ""
    user = get_user(post['user_id'])
    attachments = ' '.join([f"<a href='{file['download_url']}'>{file['name']}</a> ({file['size']} bytes, {file['mime_type']})" for file in post.get('files', [])])
    reactions = ', '.join([f"{reaction['emoji_name']} (count: {reaction['count']}, users: {', '.join(reaction['users'])})" for reaction in post.get('reactions', [])])
    edited = 'Yes' if post['edit_at'] > 0 else 'No'
    deleted = 'Yes' if post['delete_at'] > 0 else 'No'
    edited_color = 'red' if edited == 'Yes' else 'inherit'
    deleted_color = 'red' if deleted == 'Yes' else 'inherit'
    thread_indicator = f"<span class='small'>{post['root_id']}</span>" if post['root_id'] and not is_main else ""
    highlighted_message = highlight_mentions(post['message'])
    formatted_message = format_markdown(highlighted_message)
    return f"<tr class='{style}'><td>{post['id']}</td><td style='word-wrap: break-word;max-width: 375px'>{formatted_message}</td><td>{user['username']}</td><td>{datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}</td><td style='color: {edited_color};'>{edited}</td><td style='color: {deleted_color};'>{deleted}</td><td style='word-wrap: break-word;max-width: 200px'>{attachments}</td><td>{reactions}</td><td>{thread_indicator}</td></tr>"

def generate_csv(posts, channel_name):
    output_path = os.path.join('output', channel_name)
    os.makedirs(output_path, exist_ok=True)
    with open(os.path.join(output_path, f'{channel_name}.csv'), 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["ID", "Message", "Posted By", "Date", "Edited", "Deleted", "Attachments", "Reactions", "Thread"])
        for post in posts:
            writer.writerow(extract_post_details(post, is_main=True))
            for reply in sorted(post.get('replies', []), key=lambda x: x['create_at']):
                writer.writerow(extract_post_details(reply, is_main=False))

def generate_json(posts, channel_name):
    output_path = os.path.join('output', channel_name)
    os.makedirs(output_path, exist_ok=True)
    with open(os.path.join(output_path, f'{channel_name}.json'), 'w') as file:
        json.dump(posts, file, indent=4, default=str)

def extract_post_details(post, is_main):
    user = get_user(post['user_id'])
    attachments = ', '.join([f"{file['name']} ({file['size']} bytes)" for file in post.get('files', [])])
    reactions = ', '.join([f"{reaction['emoji_name']} (count: {reaction['count']}, users: {', '.join(reaction['users'])})" for reaction in post.get('reactions', [])])
    thread_indicator = f"Reply to {post['root_id']}" if post['root_id'] and not is_main else "Original Post"
    highlighted_message = highlight_mentions(post['message'])
    return [post['id'], highlighted_message, user['username'],
            datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
            'Yes' if post['edit_at'] > 0 else 'No',
            'Yes' if post['delete_at'] > 0 else 'No',
            attachments, reactions, thread_indicator]

def main():
    validate_config()
    check_system_admin()
    try:
        logging.info(f"START: Running Mattermost Channel Export ...")
        channel_name = get_channel_name(CHANNEL_ID)
        logging.info(f"Exporting posts from {channel_name}")
        posts_data = get_posts(CHANNEL_ID)
        if not FETCH_ALL:
            posts_data = filter_posts_by_date(posts_data, START_DATE, END_DATE)
        logging.info("Generating HTML, CSV, and JSON")
        generate_html(posts_data, START_DATE, END_DATE, channel_name)
        generate_csv(posts_data, channel_name)
        generate_json(posts_data, channel_name)
        logging.info("SUCCESS: HTML, CSV, and JSON saved in output folder")
    except requests.HTTPError as e:
        logging.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
