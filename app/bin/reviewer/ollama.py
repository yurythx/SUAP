import logging

import requests

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 240  # seconds


def ollama_chat(args, prompt=None):
    """Analyze code changes with Ollama."""
    key = args.llm_key
    endpoint = args.llm_url
    model = args.llm_model
    max_tokens = args.llm_max_tokens
    temperature = args.llm_temperature
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }
    data = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens,
        'temperature': temperature,
    }
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=data,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error(f'Request to Ollama failed: {e}')
        return f'Request to Ollama failed: Details: {e}'
    if response.status_code == 200:
        try:
            logger.info(response.json())
            return response.json().get('message', {}).get('content', 'No response from AI.')
        except Exception as e:
            logger.error(f'Error parsing Ollama response: {e}')
            return f'Error parsing Ollama response: {e}'
    else:
        logger.error(f'Ollama API error: {response.status_code} - {response.text}')
        return f'Ollama API error: {response.status_code} - {response.text}'
