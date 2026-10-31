import logging

import requests

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 240  # seconds


def gemini_chat(args, prompt=None):
    """Analyze code changes with Gemini."""
    key = args.llm_key
    endpoint = args.llm_url
    max_tokens = args.llm_max_tokens
    temperature = args.llm_temperature
    headers = {
        'Content-Type': 'application/json',
    }
    data = {
        'contents': [
            {
                'parts': [
                    {
                        'text': prompt or 'No prompt provided.',
                    },
                ],
            },
        ],
        'generationConfig': {
            'temperature': temperature,
            'maxOutputTokens': max_tokens,
        },
        'safetySettings': [
            {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
            {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_MEDIUM_AND_ABOVE'},
        ],
    }
    url = f'{endpoint}?key={key}'
    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.error(f'Request to Gemini failed: {e}')
        return f'Request to Gemini failed: Details: {e}'
    if response.status_code == 200:
        try:
            logger.info(response.json())
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logger.error(f'Error parsing Gemini response: {e}')
            return f'Error parsing Gemini response: {e}'
    else:
        logger.error(f'Gemini API error: {response.status_code} - {response.text}')
        return f'Gemini API error: {response.status_code} - {response.text}'
