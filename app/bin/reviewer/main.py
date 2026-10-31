import argparse
import logging

from gemini import gemini_chat
from gitlab_client import GitLabClient
from ollama import ollama_chat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def review_code(args, diff, context):
    """Analyze code changes with AI."""
    prompt = f"""
    {args.llm_prompt}

    ---
    # Input
    **Contexto do MR:** {context}

    **Diff:**
    {diff}
    """
    if args.llm_type == 'ollama':
        return ollama_chat(args, prompt) or 'No response from Ollama.'
    elif args.llm_type == 'gemini':
        return gemini_chat(args, prompt) or 'No response from Gemini.'
    return 'Unsupported LLM type specified.'


def main(args):
    logger.info(f'Starting review for MR {args.mr_id}.')
    gitlab_client = GitLabClient(args.gitlab_url, args.gitlab_token, args.project_id)
    diffs = gitlab_client.get_merge_request_diff(args.mr_id, max_tokens=(args.llm_max_tokens / 2))
    mr = gitlab_client.get_merge_request(args.mr_id)
    logger.info(f'Merge Request Title: {mr.title}')
    if diffs:
        for diff in diffs:
            review = review_code(args, diff, mr.title)
            gitlab_client.add_comment_to_mr(args.mr_id, review)


if __name__ == '__main__':
    # Create the parser
    parser = argparse.ArgumentParser(description='A simple script with command-line arguments.')
    # Add arguments
    parser.add_argument('--mr-id', type=str, help='The MR ID to review.', required=True)
    parser.add_argument('--project-id', type=int, help='The Gitlab Project ID.', required=True)
    parser.add_argument('--gitlab-url', type=str, help='The GitLab URL.', required=True)
    parser.add_argument('--gitlab-token', type=str, help='The GitLab access token.', required=True)
    parser.add_argument(
        '--llm-type',
        type=str,
        choices=['ollama', 'gemini'],
        default='gemini',
        help='The type of LLM to use for code review. Options are "ollama" or "gemini".',
        required=True,
    )
    parser.add_argument(
        '--llm-key',
        type=str,
        help='The API key for the LLM service.',
    )
    parser.add_argument(
        '--llm-model',
        type=str,
        default='gemini-1.5-pro',
        help='The model to use for the LLM.',
    )
    parser.add_argument(
        '--llm-url',
        type=str,
        help='The URL for the LLM service endpoint.',
        required=True,
    )
    parser.add_argument(
        '--llm-prompt',
        type=str,
        default="""
        Você é um engenheiro de software sênior revisando uma mudança de código de um Merge Request no Gitlab.
        Por favor, revise o seguinte código no diff abaixo. Verifique se há possíveis bugs,
        problemas de estilo ou oportunidades de otimização e refatoração. Forneça
        sugestões de melhoria com exemplos.
        Conside que:
        Este é um projeto escrito em python 3.14 e django 5.2 com algumas customizações, pois ele possui uma biblioteca
        interna chamada djtools/, que centraliza funções auxiliares reutilizáveis (ex: validações, formatações, utilitários).
        Sempre que possível, siga o princípio DRY ("Don't Repeat Yourself"): Se encontrar lógica genérica ou repetida no diff,
        avalie se ela pode ser extraída para djtools/. Seu objetivo é identificar tanto oportunidades de criação quanto de reaproveitamento
        de funções auxiliares existentes.
        """,
        help='Optional prompt to use with the LLM. If not provided, a default prompt will be used.',
    )
    parser.add_argument(
        '--llm-max-tokens',
        type=int,
        default=4000,
        help='The maximum number of tokens to generate in the response.',
    )
    parser.add_argument(
        '--llm-temperature',
        type=float,
        default=0.2,
        help='The temperature to use for the LLM response.',
    )

    # Parse the arguments
    args = parser.parse_args()

    main(args)
    logger.info('Review process completed.')
