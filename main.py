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

# -*- coding: utf-8 -*-

VERSION = "1.0.2"

import requests
import os
import csv
import json
import logging
from datetime import datetime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
CHANNEL_ID = os.getenv('CHANNEL_ID')
START_DATE = os.getenv('START_DATE')
END_DATE = os.getenv('END_DATE')
FETCH_ALL = os.getenv('FETCH_ALL', 'False').lower() == 'true'  # Checks if the environment variable is 'true'
VERIFY_SSL = os.getenv('VERIFY_SSL', 'True').lower() == 'true'  # Checks if SSL verification should be disabled
HEADERS = {'Authorization': f'Bearer {API_TOKEN}'}

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("output/mattermost_export.log"), logging.StreamHandler()])

# Session setup with retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))

# User cache
user_cache = {}

def get_user(user_id):
    if user_id in user_cache:
        return user_cache[user_id]
    url = f'{BASE_URL}/users/{user_id}'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    user_info = response.json()
    user_cache[user_id] = user_info
    return user_info

def get_file_info(file_id):
    url = f'{BASE_URL}/files/{file_id}/info'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    file_info = response.json()
    return {
        'id': file_info['id'],
        'name': file_info['name'],
        'size': file_info['size'],
        'mime_type': file_info['mime_type'],
        'download_url': f'{BASE_URL}/files/{file_id}'
    }

def get_channel_name(channel_id):
    url = f'{BASE_URL}/channels/{channel_id}'
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    channel_info = response.json()
    return channel_info['display_name']

def get_posts(channel_id, start_date=None, end_date=None):
    all_posts = {}
    page = 0
    per_page = 100

    # Initialize timestamps only if start_date and end_date are provided
    if start_date and end_date:
        start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
        end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)

    while True:
        url = f'{BASE_URL}/channels/{channel_id}/posts?page={page}&per_page={per_page}'
        response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()
        posts = data['posts']
        if not posts:
            break
        for post in posts.values():
            post_timestamp = post['create_at']
            # If FETCH_ALL is False and dates are provided, use them to filter posts
            if not FETCH_ALL and (post_timestamp < start_timestamp or post_timestamp > end_timestamp):
                continue
            add_post(all_posts, post)
        page += 1

    # Convert the dictionary to a list and sort it by create_at
    sorted_posts = sorted(all_posts.values(), key=lambda x: x['create_at'])
    return sorted_posts

def add_post(all_posts, post):
    post_details = {
        'id': post['id'],
        'message': post['message'],
        'user_id': post['user_id'],
        'create_at': post['create_at'],
        'edit_at': post.get('edit_at', 0),
        'delete_at': post.get('delete_at', 0),
        'root_id': post.get('root_id', ''),
        'parent_id': post.get('parent_id', ''),
        'files': [get_file_info(file_id) for file_id in post.get('file_ids', [])],
        'replies': []
    }
    if post_details['root_id']:  # it's a reply
        if post_details['root_id'] in all_posts:
            all_posts[post_details['root_id']]['replies'].append(post_details)
        else:  # If root post is not loaded yet, initialize it
            all_posts[post_details['root_id']] = {'replies': [post_details]}
    else:  # it's a main post
        if post['id'] in all_posts:
            all_posts[post['id']].update(post_details)
        else:
            all_posts[post['id']] = post_details

def generate_html(posts, start_date, end_date, channel_name):
    # Decide the date range text based on input
    date_range = f"From {start_date} to {end_date}" if start_date and end_date else "For all time"

    if not posts:
        logging.info("No posts available to write to HTML.")
    
    # Start HTML string with the corrected header
    html = f'''<html><head><title>Mattermost Channel Posts Export</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body>
<div class="container-flex text-center">
    <div class="row">
        <div class="col">
            <div class="row">
                <div class="col">
                    <h1>Mattermost Channel Posts Export</h1>
                </div>
            </div>
            <div class="row">
                <div class="col-10 offset-1 alert alert-secondary">
                    <h2>Posts in Channel {channel_name}</h2>
                    <h3>{date_range}</h3>
                </div>
            </div>
            <div class="row">
                <div class="col-10 offset-1 table-responsive">
                    <table class="table table-bordered table-sm">
                        <thead><tr class="table-dark"><th scope="col">ID</th><th scope="col">Message</th><th scope="col">Posted By</th><th scope="col">Date</th><th scope="col">Edited</th><th scope="col">Deleted</th><th scope="col">Attachments</th><th scope="col">Thread</th></tr></thead><tbody class="table-group-divider">'''

    for post in posts:
        html += format_post(post, is_main=True)
        for reply in sorted(post.get('replies', []), key=lambda x: x['create_at']):
            html += format_post(reply, is_main=False)

    html += '</tbody></table></div></div></div></div></div></body></html>'
    with open('output/channel_posts.html', 'w') as f:
        f.write(html)

def format_post(post, is_main):
    style = "table-active" if is_main else "table-light"
    user = get_user(post['user_id'])
    attachments = ' '.join([f"<a href='{file['download_url']}'>{file['name']}</a> ({file['size']} bytes, {file['mime_type']})" for file in post['files']])
    edited = 'Yes' if post['edit_at'] > 0 else 'No'
    deleted = 'Yes' if post['delete_at'] > 0 else 'No'
    thread_indicator = f"<span class='small'>{post['root_id']}</span>" if post['root_id'] and not is_main else ""
    return f"<tr class='{style}'><th scope='row' class='small'>{post['id']}</th><td style='word-wrap: break-word;max-width: 375px'>{post['message']}</td><td>{user['username']}</td><td>{datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}</td><td>{edited}</td><td>{deleted}</td><td style='word-wrap: break-word;max-width: 200px'>{attachments}</td><td>{thread_indicator}</td></tr>"

def generate_csv(posts):
    with open('output/channel_posts.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["ID", "Message", "Posted By", "Date", "Edited", "Deleted", "Attachments", "Thread"])
        for post in posts:
            writer.writerow(extract_post_details(post, is_main=True))
            for reply in sorted(post.get('replies', []), key=lambda x: x['create_at']):
                writer.writerow(extract_post_details(reply, is_main=False))

def generate_json(posts):
    with open('output/channel_posts.json', 'w') as file:
        json.dump(posts, file, indent=4, default=str)

def extract_post_details(post, is_main):
    user = get_user(post['user_id'])
    attachments = ', '.join([f"{file['name']} ({file['size']} bytes)" for file in post['files']])
    thread_indicator = f"Reply to {post['root_id']}" if post['root_id'] and not is_main else "Original Post"
    return [post['id'], post['message'], user['username'],
            datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
            'Yes' if post['edit_at'] > 0 else 'No',
            'Yes' if post['delete_at'] > 0 else 'No',
            attachments, thread_indicator]

def main():
    try:
        channel_name = get_channel_name(CHANNEL_ID)
        posts_data = get_posts(CHANNEL_ID, START_DATE if not FETCH_ALL else None, END_DATE if not FETCH_ALL else None)
        generate_html(posts_data, START_DATE, END_DATE, channel_name)
        generate_csv(posts_data)
        generate_json(posts_data)
        logging.info("Output files have been generated successfully.")
    except requests.HTTPError as e:
        logging.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
