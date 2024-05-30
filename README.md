# Mattermost Channel Export

A containerized application designed to fetch and export posts from a specified Mattermost channel via the API. Generating a HTML, CSV, and JSON exports containing all the messages posted or within a specified date range.

## Prerequisites

Before you begin, you will need:

- Docker installed on your machine.

- An API token from your Mattermost server.

- The Base URL of your Mattermost server.

- The Channel ID of the channel from which you want to export posts.

## Configuration

1. **Environment Setup:**

	- Create a `.env` file with the necessary configurations:

```bash
API_TOKEN=your_api_token_here
BASE_URL=https://your-mattermost-url.com/api/v4
CHANNEL_ID=your_channel_id_here
FETCH_ALL=false # Set true to ignore dates below and fetch all posts
START_DATE=2023-01-01
END_DATE=2023-12-31
VERIFYSSL=true # Set false to ignore SSL errors
DEBUG_MODE=false  # Set to true to enable debug logging
TZ=UTC # Set to your logging timezone
```

Replace the placeholder values with your API token, base URL, channel ID, and the desired date range.

## Usage

The container will generate an HTML file named `posts.html`, a CSV named `posts.csv` and a JSON named `posts.json` inside the `output\<CHANNEL_NAME>` folder inside the working directory of the Docker container. To access the files outside of the container, mount a volume to your Docker container:

```bash
docker run --env-file .env -v $(pwd)/output:/app/output ghcr.io/maxwellpower/mm-channel-export
```

The above command will save the `posts.html`, `posts.csv`, and `posts.json` to the `output\<CHANNEL_NAME>` directory in your current folder on your host machine.

## Troubleshooting

If you encounter any issues, ensure your API token has the necessary permissions and that the environment variables are correctly set. Check the Docker logs for error messages:

```bash
docker logs [container_id]
```
