FROM apify/actor-python:3.11

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src ./src

# Set working directory
WORKDIR /usr/src/app

# Run the MCP server
CMD ["python", "-m", "src.main"]
