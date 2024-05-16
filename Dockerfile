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

FROM python:3.9-slim

# Metadata
LABEL maintainer="maxwell.power@mattermost.com"
LABEL org.opencontainers.image.title="mm-channel-export"
LABEL org.opencontainers.image.description="Export Posts from a Channel"
LABEL org.opencontainers.image.authors="Maxwell Power"
LABEL org.opencontainers.image.source="https://github.com/maxwellpower/mm-channel-export"
LABEL org.opencontainers.image.licenses="MIT"

# Create and switch to a new user
RUN adduser --disabled-password --gecos '' mmuser
USER mmuser

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python script
COPY main.py .

CMD ["python", "main.py"]
