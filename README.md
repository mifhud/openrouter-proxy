# Anthropic API Proxy

A simple proxy server for Kilo.ai Anthropic-compatible API that helps bypass rate limits
by rotating through multiple API keys in a round-robin fashion.

## Features

- Proxies all requests to Kilo.ai Anthropic-compatible API (`/v1/messages`, etc.)
- Rotates multiple API keys to bypass rate limits
- Automatically disables API keys temporarily when rate limits are reached
- Streams responses chunk by chunk for efficient data transfer
- Simple authentication via `x-api-key` header (Anthropic SDK compatible)
- Compatible with Anthropic SDK by setting `base_url` to the proxy URL

## Setup

1. Clone the repository
2. Create a virtual environment and install dependencies:
    ```
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```
3. Create a configuration file:
    ```
    cp config.yml.example config.yml
    ```
4. Edit `config.yml` to add your Kilo.ai API keys and configure the server

## Configuration

The `config.yml` file supports the following settings:

```yaml
# Server settings
server:
  host: "0.0.0.0"  # Interface to bind to
  port: 5003        # Port to listen on
  access_key: "your_local_access_key_here"  # Key for accessing the local proxy (clients send as x-api-key)
  log_level: "INFO"
  http_log_level: "INFO"

# Kilo.ai API keys (Anthropic-compatible)
anthropic:
  keys:
    - "your-kilo-api-key-1"
    - "your-kilo-api-key-2"
    - "your-kilo-api-key-3"

  key_selection_strategy: "round-robin"
  key_selection_opts: []

  # Kilo.ai Anthropic-compatible base URL
  base_url: "https://api.kilo.ai/v1"

  public_endpoints:
    - "/v1/models"

  rate_limit_cooldown: 14400  # 4 hours

requestProxy:
  enabled: false
  url: "socks5://username:password@example.com:1080"
```

## Usage

### Running Manually

Start the server:
```
python main.py
```

The proxy will be available at `http://localhost:5003/v1` (or the host/port configured in your config file).

### Using with Anthropic SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:5003",
    api_key="your_local_access_key_here",  # proxy access key
)

message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
print(message.content[0].text)
```

### Installing as a Systemd Service

For Linux systems with systemd, you can install the proxy as a system service:

1. Make sure you've created and configured your `config.yml` file
2. Run the installation script:

```sudo ./service_install.sh``` or ```sudo ./service_install_venv.sh``` for venv.

This will create a systemd service that starts automatically on boot.

To check the service status:
```
sudo systemctl status kilocode-proxy
```

To view logs:
```
sudo journalctl -u kilocode-proxy -f
```

To uninstall the service:
```
sudo ./service_uninstall.sh
```

### Authentication

Add your local access key to requests via the `x-api-key` header:
```
x-api-key: your_local_access_key_here
anthropic-version: 2023-06-01
```

## API Endpoints

The proxy supports all Anthropic API v1 endpoints through:

- `/v1/{path}` - Proxies all requests to Kilo.ai Anthropic-compatible API
- `/health` - Health check endpoint that returns `{"status": "ok"}`

### Example: Send a message

```bash
curl -X POST http://localhost:5003/v1/messages \
  -H "x-api-key: your_local_access_key_here" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```
