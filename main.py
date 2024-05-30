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

# File: main.py

import requests  # type: ignore
import urllib3  # type: ignore
import markdown  # type: ignore

from requests.adapters import HTTPAdapter  # type: ignore
from requests.packages.urllib3.util.retry import Retry  # type: ignore
from urllib3.util import parse_url  # type: ignore
from dotenv import load_dotenv  # type: ignore

import os
import csv
import json
import logging
import re
import html

from datetime import datetime
from collections import defaultdict

# Load environment variables
load_dotenv()

# Configuration
API_TOKEN = os.getenv("API_TOKEN")
BASE_URL = os.getenv("BASE_URL")
CHANNEL_ID = os.getenv("CHANNEL_ID")
START_DATE = os.getenv("START_DATE")
END_DATE = os.getenv("END_DATE")
FETCH_ALL = os.getenv("FETCH_ALL", "False").lower() == "true"
VERIFY_SSL = os.getenv("VERIFY_SSL", "True").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# Set up logging
log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("output/export.log"), logging.StreamHandler()],
)

# Suppress SSL warnings if VERIFY_SSL is False
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Session setup with retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))

# User cache
user_cache = {}
is_system_admin = False


# Validate the environment variables and version information
def validate_config():
    if not API_TOKEN or not BASE_URL or not CHANNEL_ID:
        logging.critical(
            "FAILED: OOPS! Configuration is not valid!\nPlease ensure API_TOKEN, BASE_URL, and CHANNEL_ID envrionment variables are set.\nSee README for usage details."
        )
        exit(1)
    else:
        # Get the script version data
        with open("version.json") as vd:
            version_data = json.load(vd)
            global script_version
            global bootstrap_version
            script_version = version_data["version"]
            bootstrap_version = version_data["bootstrap_version"]
            api_version = version_data["api_version"]
        if script_version:
            # Filter the URL just incase
            global server_domain
            global API_ENDPOINT
            server_domain = parse_url(BASE_URL).host
            API_ENDPOINT = f"{parse_url(BASE_URL).scheme}://{server_domain}/api/v{api_version}"
            logging.info(f"Using API_ENDPOINT: {API_ENDPOINT}")
            logging.info("Configuration Loaded Successfully")
        else:
            logging.critical("FAILED: Configuration Not Loaded")
            exit(1)


# Check the API connection and get the server version
def get_server_version():
    url = f"{API_ENDPOINT}/system/ping"
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    response_json = response.json()
    api_version = response.headers.get("X-Version-Id", "Unknown version")
    version = (
        ".".join(api_version.split(".")[:3])
        if "Unknown version" not in api_version
        else api_version
    )
    if "Unknown version" in api_version:
        logging.critical("API Connection Failed!")
        if DEBUG_MODE:
            logging.debug(f"Response Headers: {response.headers}")
            logging.debug(f"Response: {response_json}")

        exit(1)
    else:
        global server_version
        server_version = version
        logging.info(f"Successfully connected to Mattermost {version}")


# Get current user and check roles
def check_system_admin():

    # Get the details for the current user
    def get_current_user():
        url = f"{API_ENDPOINT}/users/me"
        response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
        response.raise_for_status()
        user_info = response.json()

        if DEBUG_MODE:
            logging.debug(f"Current User: {user_info}")

        return user_info

    global is_system_admin
    global username
    current_user = get_current_user()
    roles = current_user.get("roles", "")
    username = current_user.get("username", "")
    is_system_admin = "system_admin" in roles
    if is_system_admin:
        logging.info(f"{username} is a system admin. Deleted posts will be exported!")
    else:
        logging.warning(
            f"{username} is not a system admin. Deleted posts will not be exported!"
        )


# Get details for a system user
def get_user(user_id):
    if user_id in user_cache:
        return user_cache[user_id]
    url = f"{API_ENDPOINT}/users/{user_id}"
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    user_info = response.json()
    user_cache[user_id] = user_info

    if DEBUG_MODE:
        logging.debug(f"Retrieved details for user: {user_info}")

    return user_info


# Get the name of the channel
def get_channel_name(channel_id):
    url = f"{API_ENDPOINT}/channels/{channel_id}"
    response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
    response.raise_for_status()
    channel_info = response.json()

    if DEBUG_MODE:
        logging.debug(f"Retreived details for Channel: {channel_info}")

    return channel_info["display_name"]


# Export the channel posts
def get_posts(channel_id):

    def fetch_thread_posts(root_id):
        thread_posts = []
        url = f"{API_ENDPOINT}/posts/{root_id}/thread"
        response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()

        if DEBUG_MODE:
            logging.debug(f"Thread Posts: {data}")

        thread_posts.extend(data.get("posts", {}).values())
        return thread_posts

    all_posts = []
    post_dict = {}
    page = 0
    per_page = 100

    while True:
        params = {"page": page, "per_page": per_page}
        if is_system_admin:
            params["include_deleted"] = (
                "true"  # Include deleted posts for system admins
            )
        url = f"{API_ENDPOINT}/channels/{channel_id}/posts"
        response = session.get(url, headers=HEADERS, params=params, verify=VERIFY_SSL)
        response.raise_for_status()
        data = response.json()

        if DEBUG_MODE:
            logging.debug(f"Posts: {data}")

        logging.info(f"Processed Page: {page}, Posts: {len(data.get('posts', {}))}")

        posts = data.get("posts", {})
        if not posts:
            break
        all_posts.extend(posts.values())
        post_dict.update(posts)

        # Check if the total posts retrieved is less than per_page. If so, break the loop.
        if len(posts) < per_page:
            break
        page += 1

    # Fetch threaded posts
    for post in all_posts:
        root_id = post.get("root_id")
        if root_id and root_id not in post_dict:
            thread_posts = fetch_thread_posts(root_id)
            for tpost in thread_posts:
                post_dict[tpost["id"]] = tpost

    sorted_posts = sorted(post_dict.values(), key=lambda x: x["create_at"])

    if DEBUG_MODE:
        logging.debug(f"Sorted Posts: {sorted_posts}")

    return sorted_posts


# Filter the posts by date
def filter_posts_by_date(posts, start_date, end_date):
    start_timestamp = (
        int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        if start_date
        else None
    )
    end_timestamp = (
        int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        if end_date
        else None
    )
    filtered_posts = []

    for post in posts:
        post_timestamp = post["create_at"]
        if (start_timestamp and post_timestamp < start_timestamp) or (
            end_timestamp and post_timestamp > end_timestamp
        ):
            continue
        filtered_posts.append(post)

    if DEBUG_MODE:
        logging.debug(f"Filtered Posts: {filtered_posts}")

    return filtered_posts


# Add a post to the final export
def add_post(all_posts, post):

    # Get the post reactions
    def get_reactions(post_id):

        if DEBUG_MODE:
            logging.debug(f"Fetching reactions for post_id: {post_id}")

        url = f"{API_ENDPOINT}/posts/{post_id}/reactions"
        response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
        response.raise_for_status()
        reactions = response.json() or []

        if DEBUG_MODE:
            logging.debug(f"Post Reactions: {reactions}")

        reaction_details = defaultdict(list)

        for reaction in reactions:
            user_info = get_user(reaction["user_id"])
            reaction_details[reaction["emoji_name"]].append(user_info["username"])

        return [
            {"emoji_name": emoji, "users": users, "count": len(users)}
            for emoji, users in reaction_details.items()
        ]

    # Get the attachment file info
    def get_file_info(file_id):
        if DEBUG_MODE:
            logging.debug(f"Fetching file info for file_id: {file_id}")
        url = f"{API_ENDPOINT}/files/{file_id}/info"
        try:
            response = session.get(url, headers=HEADERS, verify=VERIFY_SSL)
            response.raise_for_status()
            file_info = response.json()
            logging.debug(f"Retrieved file info: {file_info}")
            return {
                "id": file_info.get("id"),
                "name": file_info.get("name"),
                "size": file_info.get("size"),
                "mime_type": file_info.get("mime_type"),
                "upload_time": (
                    datetime.fromtimestamp(file_info["create_at"] / 1000).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if file_info.get("create_at")
                    else "N/A"
                ),
                "uploader_id": file_info.get("user_id"),
                "download_url": f"{API_ENDPOINT}/files/{file_id}",
            }
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"File not found: {file_id}, post may have been deleted?")
                return None
            else:
                logging.error(
                    f"HTTP error occurred while fetching file info: {e.response.status_code} - {e.response.text}"
                )
                raise

    post_details = {
        "id": post["id"],
        "message": post.get("message", ""),
        "user_id": post["user_id"],
        "create_at": post["create_at"],
        "edit_at": post.get("edit_at", 0),
        "delete_at": post.get("delete_at", 0),
        "root_id": post.get("root_id", ""),
        "parent_id": post.get("parent_id", ""),
        "files": [
            file_info
            for file_id in post.get("file_ids", [])
            if (file_info := get_file_info(file_id))
        ],
        "reactions": get_reactions(post["id"]),
        "replies": [],
    }
    if post_details["root_id"]:
        if post_details["root_id"] in all_posts:
            all_posts[post_details["root_id"]]["replies"].append(post_details)
        else:
            all_posts[post_details["root_id"]] = {"replies": [post_details]}
    else:
        if post["id"] in all_posts:
            all_posts[post["id"]].update(post_details)
        else:
            all_posts[post["id"]] = post_details


# Generate the HTML source
def generate_html(posts, start_date, end_date, channel_name):

    def get_current_datetime():
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    def format_post(post, is_main):

        def highlight_mentions(message):
            return re.sub(
                r"(@[a-zA-Z0-9_.-]+)", r'<span style="color: blue;">\1</span>', message
            )

        def format_markdown(message):
            return markdown.markdown(message, extensions=["fenced_code"])

        def format_modal_markdown(message):
            return markdown.markdown(message, extensions=["extra"])

        style = "table-active" if is_main else "table-light"
        post_id_formatted = f"<strong>{post['id']}</strong" if is_main else post["id"]
        user = get_user(post["user_id"])
        attachments = " ".join(
            [
                f"<a href='{file['download_url']}'>{file['name']}</a> ({file['size']} bytes, {file['mime_type']})"
                for file in post.get("files", [])
            ]
        )
        reactions = ", ".join(
            [
                f"{reaction['emoji_name']} (count: {reaction['count']}, users: {', '.join(reaction['users'])})"
                for reaction in post.get("reactions", [])
            ]
        )
        edited = "Yes" if post["edit_at"] > 0 else "No"
        deleted = "Yes" if post["delete_at"] > 0 else "No"
        edited_color = "red" if edited == "Yes" else "inherit"
        deleted_color = "red" if deleted == "Yes" else "inherit"
        thread_indicator = f"{post['root_id']}" if post["root_id"] else ""
        raw_message = post["message"]
        highlighted_message = highlight_mentions(raw_message)
        formatted_message = format_markdown(highlighted_message)
        formatted_modal_message = format_modal_markdown(highlighted_message)

        if is_system_admin:
            modal_content = html.escape(
                f"<strong>Formatted Message:</strong> {formatted_modal_message}<br><strong>Post ID:</strong> {post['id']}<br><strong>Posted By:</strong> {user['username']}<br><strong>Date:</strong> {datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}<br><strong>Edited:</strong> {edited}<br><strong>Deleted:</strong> {deleted}<br><strong>Attachments:</strong> {attachments}<br><strong>Reactions:</strong> {reactions}<br><strong>Parent:</strong> {thread_indicator}<br><strong>Raw Message:</strong><textarea rows='5' cols='75'>{raw_message}</textarea>"
            )
            formatted_html_output = f"<tr class='{style} table-row' data-post_id='{post['id']}' data-details='{modal_content}'><th scope='row'>{post_id_formatted}</td><td style='word-wrap: break-word;max-width: 350px'>{formatted_message}</td><td>{user['username']}</td><td>{datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}</td><td style='color: {edited_color};'>{edited}</td><td style='color: {deleted_color};'>{deleted}</td><td style='word-wrap: break-word;max-width: 200px'>{attachments}</td><td>{reactions}</td><td>{thread_indicator}</td></tr>"
        else:
            modal_content = html.escape(
                f"<strong>Formatted Message:</strong> {formatted_modal_message}<br><strong>Post ID:</strong> {post['id']}<br><strong>Posted By:</strong> {user['username']}<br><strong>Date:</strong> {datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}<br><strong>Edited:</strong> {edited}<br><strong>Attachments:</strong> {attachments}<br><strong>Reactions:</strong> {reactions}<br><strong>Parent:</strong> {thread_indicator}<br><strong>Raw Message:</strong><textarea rows='5' cols='75'>{raw_message}</textarea>"
            )
            formatted_html_output = f"<tr class='{style} table-row' data-post_id='{post['id']}' data-details='{modal_content}'><th scope='row'>{post_id_formatted}</td><td style='word-wrap: break-word;max-width: 350px'>{formatted_message}</td><td>{user['username']}</td><td>{datetime.fromtimestamp(post['create_at'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}</td><td style='color: {edited_color};'>{edited}</td><td style='word-wrap: break-word;max-width: 200px'>{attachments}</td><td>{reactions}</td><td>{thread_indicator}</td></tr>"

        return formatted_html_output

    date_range = "For all time" if FETCH_ALL else f"From {start_date} to {end_date}"
    report_datetime = get_current_datetime()
    report_username = (
        f"{username} <span class='text-danger'>(System Admin)</span>"
        if is_system_admin
        else f"{username}"
    )

    if not posts:
        logging.info("No posts available to write to HTML.")

    html_content = f"""
<html>
<head>
    <title>Mattermost Channel Export - {channel_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@{bootstrap_version}/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .table-row {{
            cursor: pointer;
        }}
        .modal-body {{
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
<div class="container-flex">
    <div class="row">
        <div class="col">
            <div class="header">
                <div class="row">
                    <div class="col">
                        <div class="text-center my-4">
                            <h1>Mattermost Channel Export</h1>
                            <h2>Posts in Channel: <code>{channel_name}</code></h2>
                            <h3>{date_range}<h3>
                        </div>
                    </div>
                </div>
            </header>
            <div class="row alert alert-light">
                <div class="col-10 offset-1">
                    <div class="table-responsive">
                        <table class="table table-bordered table-hover table-sm"><caption>{"All posts" if FETCH_ALL else f"Posts from {start_date} to {end_date}"} in {channel_name} as of {report_datetime}</caption>"""

    if is_system_admin:
        html_content += '<thead><tr class="table-dark"><th>ID</th><th>Message</th><th>Posted By</th><th>Date</th><th>Edited</th><th>Deleted</th><th>Attachments</th><th>Reactions</th><th>Parent</th></tr></thead>'
    else:
        html_content += '<thead><tr class="table-dark"><th>ID</th><th>Message</th><th>Posted By</th><th>Date</th><th>Edited</th><th>Attachments</th><th>Reactions</th><th>Parent</th></tr></thead>'

    html_content += '<tbody class="table-group-divider">'

    for post in posts:
        if post["root_id"] == "":
            html_content += format_post(post, is_main=True)
        else:
            html_content += format_post(post, is_main=False)
        for reply in sorted(post.get("replies", []), key=lambda x: x["create_at"]):
            html_content += format_post(reply, is_main=False)

    html_content += "</tbody>"
    html_content += f"""
                        </table>
                    </div>
                </div>
            </div>
            <footer class="footer">
                <div class="row">
                    <div class="col">
                        <div class="text-center my-4">
                            <p>{channel_name} exported on {report_datetime} by {report_username}</p>
                            <p>Mattermost Server: {server_domain} Version: v{server_version}</p>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    </div>
</div>
"""

    html_content += """
<div class="modal fade" id="detailsModal" tabindex="-1" aria-labelledby="detailsModalLabel" aria-hidden="true">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="detailsModalLabel">Post Details</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body" id="modal-body-content">
      </div>
    </div>
  </div>
</div>
"""

    html_content += f'<script src="https://cdn.jsdelivr.net/npm/bootstrap@{bootstrap_version}/dist/js/bootstrap.bundle.min.js"></script>'

    html_content += """
<script>
function showModal(content) {
    document.getElementById('modal-body-content').innerHTML = content;
    var myModal = new bootstrap.Modal(document.getElementById('detailsModal'), {});
    myModal.show();
}

document.querySelectorAll('.table-row').forEach(row => {
    row.addEventListener('click', () => {
        showModal(row.dataset.details);
    });
});
</script>
</body>
</html>
"""

    output_path = os.path.join("output", channel_name)
    os.makedirs(output_path, exist_ok=True)
    with open(os.path.join(output_path, f"posts.html"), "w") as f:
        f.write(html_content)


# Generate the CSV source
def generate_csv(posts, channel_name):

    # Format the post row
    def format_csv_post(post, is_main):
        user = get_user(post["user_id"])
        attachments = ", ".join(
            [f"{file['name']} ({file['size']} bytes)" for file in post.get("files", [])]
        )
        reactions = ", ".join(
            [
                f"{reaction['emoji_name']} (count: {reaction['count']}, users: {', '.join(reaction['users'])})"
                for reaction in post.get("reactions", [])
            ]
        )
        thread_indicator = (
            f"{post['root_id']}" if post["root_id"] and not is_main else ""
        )
        message = post["message"]
        if is_system_admin:
            formatted_output = [
                post["id"],
                message,
                user["username"],
                datetime.fromtimestamp(post["create_at"] / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "Yes" if post["edit_at"] > 0 else "No",
                "Yes" if post["delete_at"] > 0 else "No",
                attachments,
                reactions,
                thread_indicator,
            ]
        else:
            formatted_output = [
                post["id"],
                message,
                user["username"],
                datetime.fromtimestamp(post["create_at"] / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "Yes" if post["edit_at"] > 0 else "No",
                attachments,
                reactions,
                thread_indicator,
            ]

        return formatted_output

    output_path = os.path.join("output", channel_name)
    os.makedirs(output_path, exist_ok=True)
    with open(os.path.join(output_path, f"posts.csv"), "w", newline="") as file:
        writer = csv.writer(file)

        if is_system_admin:
            writer.writerow(
                [
                    "ID",
                    "Message",
                    "Posted By",
                    "Date",
                    "Edited",
                    "Deleted",
                    "Attachments",
                    "Reactions",
                    "Parent",
                ]
            )
        else:
            writer.writerow(
                [
                    "ID",
                    "Message",
                    "Posted By",
                    "Date",
                    "Edited",
                    "Attachments",
                    "Reactions",
                    "Parent",
                ]
            )

        for post in posts:
            writer.writerow(format_csv_post(post, is_main=True))
            for reply in sorted(post.get("replies", []), key=lambda x: x["create_at"]):
                writer.writerow(format_csv_post(reply, is_main=False))


# Generate the CSV source
def generate_json(posts, channel_name):
    output_path = os.path.join("output", channel_name)
    os.makedirs(output_path, exist_ok=True)
    with open(os.path.join(output_path, f"posts.json"), "w") as file:
        json.dump(posts, file, indent=4, default=str)


# The main program
def main():
    logging.info(f"Validating Configuration Settings ...")
    validate_config()
    try:
        logging.info(f"Running Mattermost Channel Export v{script_version} ...")
        get_server_version()
        check_system_admin()
        channel_name = get_channel_name(CHANNEL_ID)
        logging.info(f"Exporting posts from Channel: {channel_name} ...")
        posts_data = get_posts(CHANNEL_ID)
        logging.info("Formatting and Filtering Posts ...")

        all_posts = {}
        for post in posts_data:
            add_post(all_posts, post)

        posts_data = list(all_posts.values())

        if not FETCH_ALL:
            logging.info(f"Filtering posts between {START_DATE} and {END_DATE}")
            posts_data = filter_posts_by_date(posts_data, START_DATE, END_DATE)
        else:
            logging.info(f"FETCH_ALL enabled, skipping filtering")

        logging.info("Generating HTML, CSV, and JSON ...")
        generate_html(posts_data, START_DATE, END_DATE, channel_name)
        generate_csv(posts_data, channel_name)
        generate_json(posts_data, channel_name)
        logging.info("SUCCESS: HTML, CSV, and JSON saved in output folder")

    except requests.HTTPError as e:
        logging.error(
            f"HTTP error occurred: {e.response.status_code} - {e.response.text}"
        )
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
