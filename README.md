# Mattermost Channel Export

This Docker container is designed to fetch and export posts from a specified Mattermost channel using the Mattermost API. It generates an HTML, CSV, and JSON report containing the messages posted within a specified date range.

## Prerequisites

Before you begin, you will need:

- Docker installed on your machine.

- An API token from your Mattermost server.

- The Base URL of your Mattermost server.

- The Channel ID of the channel from which you want to export posts.

- Start and End dates for the data export range. 

## Configuration

1. **Environment Setup:**

	- Create a `.env` file with the necessary configurations:

```txt
API_TOKEN=your_api_token_here
BASE_URL=https://your-mattermost-url.com/api/v4
CHANNEL_ID=your_channel_id_here
FETCH_ALL=false # Set true to ignore dates below and fetch all posts
START_DATE=2023-01-01
END_DATE=2023-12-31
```  

Replace the placeholder values with your API token, base URL, channel ID, and the desired date range.

2. **Pull the Docker Image:**

Pull the Docker image from GitHub Container Registry by running:

```bash
docker pull ghcr.io/maxwellpower/mm-channel-export:latest
```

3. **Run the Container:**

Use the following command to run the container, utilizing the environment variables from your .env file:

```bash
docker run --env-file .env ghcr.io/maxwellpower/mm-channel-export
```

This command will configure the Docker container using the environment variables defined in the .env file.

## Output

The script will generate an HTML file named channel_posts.html and channel_posts.csv in the working directory inside the Docker container. To access the file outside of the Docker environment, consider mounting a volume to your Docker container:

```bash
docker run --env-file .env -v $(pwd)/output:/app/output ghcr.io/maxwellpower/mm-channel-export
```

This will save the channel_posts.html and channel_posts.csv to the output directory on your host machine.

## Troubleshooting

If you encounter any issues, ensure your API token has the necessary permissions and that the environment variables are correctly set. Check the Docker logs for error messages:

```bash
docker logs [container_id]
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
