from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from processo_seletivo.models import WebService
import socket
import time
from requests import RequestException
import xmltodict
from xml.dom import minidom
from urllib.parse import urlparse
import zlib
import os
import subprocess


class Command(BaseCommand):
    help = 'Testa conectividade com as APIs do SGC usadas para importação de edital'

    def add_arguments(self, parser):
        parser.add_argument('edital_id', type=int, help='ID da solução (código do edital no SGC, não o ID da tabela)')
        parser.add_argument('webservice_id', type=int, help='ID do WebService cadastrado no SUAP')

    def handle(self, *args, **options):
        edital_id = options['edital_id']
        webservice_id = options['webservice_id']

        try:
            webservice = WebService.objects.get(id=webservice_id)
        except WebService.DoesNotExist:
            raise CommandError(f'WebService com ID {webservice_id} não encontrado')

        self.stdout.write(self.style.SUCCESS(f'\n🔍 Diagnóstico de Edital {edital_id} usando WebService "{webservice.descricao}"\n'))

        diagnostico = DiagnosticoEdital(webservice, edital_id, self)
        diagnostico.executar()


class DiagnosticoEdital:
    def __init__(self, webservice, edital_codigo, command):
        self.webservice = webservice
        self.edital_codigo = edital_codigo
        self.resultados = {}
        self.timeout = getattr(settings, 'REQUESTS_TIMEOUT', 10)
        self.command = command
        self.stdout = command.stdout
        self.style = command.style
        self.primer_codigo_candidato = None
        self._editais_content = None

    def _decode_content(self, content):
        if isinstance(content, bytes):
            try:
                return content.decode('utf-8')
            except UnicodeDecodeError:
                return content.decode('latin-1')
        return content

    def _is_zlib(self, content):
        if not isinstance(content, bytes | bytearray) or len(content) < 2:
            return False
        return content[0] == 0x78 and content[1] in (0x01, 0x5E, 0x9C, 0xDA)

    def _try_decompress(self, content):
        try:
            return True, zlib.decompress(content)
        except Exception as exc:
            return False, exc

    def _is_numeric(self, value):
        try:
            return str(value).isdigit()
        except Exception:
            return False

    def _diagnostico_avancado_rede(self, url):
        """Testa latência, throughput e conectividade TCP para investigar problemas de rede/firewall"""
        parsed = urlparse(url)
        host = parsed.netloc.split(':')[0]
        port = 443 if parsed.scheme == 'https' else 80

        # Teste 1: Latência com ping
        self.stdout.write('\n      📡 Teste de Latência (PING):')
        try:
            result = subprocess.run(['ping', '-c', '3', '-W', '2000', host], check=False, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'min/avg/max' in line or 'min = ' in line:
                        self.stdout.write(f'         {line.strip()}')
                        break
            else:
                self.stdout.write('         ❌ Host não responde a PING')
        except Exception as e:
            self.stdout.write(f'         ⚠️  Não foi possível executar ping: {e!s}')

        # Teste 2: Conectividade TCP na porta
        self.stdout.write(f'\n      🔌 Teste de Conectividade TCP (porta {port}):')
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            resultado = sock.connect_ex((host, port))
            sock.close()

            if resultado == 0:
                self.stdout.write(f'         ✓ Porta {port} está aberta e acessível')
            else:
                self.stdout.write(f'         ❌ Não foi possível conectar na porta {port}')
                self.stdout.write('            💡 Possível bloqueio por firewall ou serviço indisponível')
        except Exception as e:
            self.stdout.write(f'         ⚠️  Erro ao testar conectividade TCP: {e!s}')

        # Teste 3: Traceroute para ver onde a conexão falha
        self.stdout.write('\n      🗺️  Teste de Rota (TRACEROUTE):')
        try:
            cmd = 'tracert' if os.name == 'nt' else 'traceroute'
            args = [cmd, '-m', '15', '-w', '2000', host] if os.name != 'nt' else [cmd, '-h', '15', host]
            result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=20)
            lines = result.stdout.split('\n')
            # Mostra primeiras 5 linhas
            shown = 0
            for line in lines:
                if line.strip() and shown < 5:
                    self.stdout.write(f'         {line.strip()}')
                    shown += 1
            if len(lines) > 6 and shown >= 5:
                self.stdout.write('         ...')
        except Exception as e:
            self.stdout.write(f'         ⚠️  Traceroute não disponível: {e!s}')

        # Resumo de análise
        self.stdout.write('\n      💡 Análise do Problema:')
        self.stdout.write('         • Se PING falha: Host não está acessível (DNS/roteamento)')
        self.stdout.write(f'         • Se TCP porta {port} falha: Firewall/NSG pode estar bloqueando')
        self.stdout.write('         • Se latência > 1000ms: Rede muito lenta ou congestionada')
        self.stdout.write('         • Se traceroute congela: Bloqueio em algum hop da rota')

    def _find_candidate_code(self, obj, parent_key=None):
        if isinstance(obj, dict):
            if 'inscricao' in obj and self._is_numeric(obj['inscricao']):
                return obj['inscricao']
            if 'codigo_candidato' in obj and self._is_numeric(obj['codigo_candidato']):
                return obj['codigo_candidato']
            if parent_key in ('candidato', 'candidatos', 'candidato_vaga', 'candidatos_vaga'):
                if 'codigo' in obj and self._is_numeric(obj['codigo']):
                    return obj['codigo']
            for key, value in obj.items():
                found = self._find_candidate_code(value, key)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._find_candidate_code(item, parent_key)
                if found:
                    return found
        return None

    def _extract_inscricao_from_edital_xml(self, content):
        try:
            xml_text = self._decode_content(content)
            doc = minidom.parseString(xml_text)
            candidatos = doc.getElementsByTagName('candidato')
            if candidatos:
                inscricao_nodes = candidatos[0].getElementsByTagName('inscricao')
                if inscricao_nodes and inscricao_nodes[0].firstChild:
                    return inscricao_nodes[0].firstChild.nodeValue
            candidatos_vaga = doc.getElementsByTagName('candidato-vaga')
            if candidatos_vaga:
                inscricao_nodes = candidatos_vaga[0].getElementsByTagName('inscricao')
                if inscricao_nodes and inscricao_nodes[0].firstChild:
                    return inscricao_nodes[0].firstChild.nodeValue
        except Exception:
            return None
        return None

    def testar_dns(self, url):
        """Testa resolução DNS da URL"""
        try:
            domain = urlparse(url).netloc
            socket.gethostbyname(domain)
            return True, None
        except socket.gaierror as e:
            return False, f'DNS falhou: {e!s}'
        except Exception as e:
            return False, f'Erro DNS: {e!s}'

    def testar_conectividade(self, url, headers, timeout=None):
        """Testa conectividade HTTP com a URL"""
        try:
            import requests

            if timeout is None:
                timeout = self.timeout
            inicio = time.time()
            response = requests.get(url, headers=headers, timeout=timeout)
            tempo = round(time.time() - inicio, 2)

            if response.status_code == 200:
                return True, f'200 OK ({tempo}s)', response.content
            elif response.status_code == 504:
                return False, '504 Gateway Timeout - SGC pode estar indisponível', None
            else:
                return False, f'{response.status_code} {response.reason}', None
        except requests.Timeout:
            return False, f'Timeout ({timeout}s) - conexão muito lenta ou SGC indisponível', None
        except requests.ConnectionError as e:
            return False, f'Erro de conexão: {e!s}', None
        except RequestException as e:
            return False, f'Erro na requisição: {e!s}', None

    def validar_xml(self, content):
        """Valida se o conteúdo é XML válido"""
        try:
            content = self._decode_content(content)
            xmltodict.parse(content)
            return True, 'XML válido'
        except Exception as e:
            return False, f'XML inválido: {e!s}'

    def testar_api_editais(self):
        """Testa endpoint de listagem de editais"""
        self.stdout.write('\n📋 Testando: Listagem de Editais')
        self.stdout.write(f'   URL: {self.webservice.url_editais}')

        headers = {'Authorization': f'Token {self.webservice.token or ""}'}

        # Teste DNS
        sucesso_dns, msg_dns = self.testar_dns(self.webservice.url_editais)
        self.stdout.write(f'   {"✓" if sucesso_dns else "❌"} DNS: {msg_dns if msg_dns and not sucesso_dns else "OK"}')
        if not sucesso_dns:
            return False

        # Teste HTTP
        sucesso_http, msg_http, content = self.testar_conectividade(self.webservice.url_editais, headers)
        self.stdout.write(f'   {"✓" if sucesso_http else "❌"} HTTP: {msg_http}')
        if not sucesso_http:
            return False

        # Valida XML e extrai primeiro candidato para teste posterior
        self._editais_content = content
        content_for_parse = content
        if self._is_zlib(content_for_parse):
            ok, decompressed = self._try_decompress(content_for_parse)
            if ok:
                content_for_parse = decompressed
            else:
                self.stdout.write('   ⚠️  Conteúdo parece compactado no endpoint de editais')

        sucesso_xml, msg_xml = self.validar_xml(content_for_parse)
        self.stdout.write(f'   {"✓" if sucesso_xml else "❌"} XML: {msg_xml}')

        return sucesso_http and sucesso_xml

    def testar_api_edital(self):
        """Testa endpoint de importação de edital específico"""
        self.stdout.write(f'\n📋 Testando: Edital Específico (ID: {self.edital_codigo})')

        url = self.webservice.url_edital.format(self.edital_codigo)
        self.stdout.write(f'   URL: {url}')

        headers = {'Authorization': f'Token {self.webservice.token or ""}'}

        # Teste DNS
        sucesso_dns, msg_dns = self.testar_dns(url)
        self.stdout.write(f'   {"✓" if sucesso_dns else "❌"} DNS: {msg_dns if msg_dns and not sucesso_dns else "OK"}')
        if not sucesso_dns:
            return False

        # Teste HTTP
        sucesso_http, msg_http, content = self.testar_conectividade(url, headers)
        self.stdout.write(f'   {"✓" if sucesso_http else "❌"} HTTP: {msg_http}')

        # Se falhou com 504 ou timeout, tenta com timeout maior
        if not sucesso_http and ('504' in msg_http or 'Timeout' in msg_http):
            timeout_maior = self.timeout * 3
            self.stdout.write(f'\n   🔄 Retentando com timeout maior ({timeout_maior}s)...')
            sucesso_http, msg_http, content = self.testar_conectividade(url, headers, timeout=timeout_maior)
            self.stdout.write(f'   {"✓" if sucesso_http else "❌"} HTTP (timeout {timeout_maior}s): {msg_http}')

            # Se ainda falhar, adiciona testes diagnósticos de rede
            if not sucesso_http:
                self.stdout.write('\n   🔧 Executando diagnóstico avançado de rede...')
                self._diagnostico_avancado_rede(url)

            if not sucesso_http:
                if '504' in msg_http:
                    self.stdout.write('\n   💡 Dicas para investigar erro 504:')
                    self.stdout.write('      1. O SGC pode estar lento ou em manutenção')
                    self.stdout.write('      2. Verifique a saúde do servidor SGC')
                    self.stdout.write('      3. Tente acessar manualmente a URL no navegador')
                    self.stdout.write('      4. Verifique logs do SGC para erros internos')
                    self.stdout.write('      5. Cheque conectividade de rede entre os servidores')
                elif 'Timeout' in msg_http:
                    self.stdout.write('\n   💡 Dicas para investigar timeout:')
                    self.stdout.write('      1. A resposta do SGC está levando muito tempo')
                    self.stdout.write('      2. Verifique performance do SGC')
                    self.stdout.write('      3. Considere aumentar REQUESTS_TIMEOUT no settings')
                    self.stdout.write('      4. Verifique latência de rede: ping/traceroute')
                    self.stdout.write('      5. Analise logs de conexão do firewall')
        if not sucesso_http:
            return False

        # Verificar se está compactado
        content_for_parse = content
        if self.webservice.is_zipped:
            if not self._is_zlib(content):
                self.stdout.write('   ⚠️  is_zipped=True, mas o retorno não parece compactado')
                self.stdout.write('      💡 DICA: Verifique se o SGC está enviando conteúdo compactado')
                sucesso_xml, msg_xml = self.validar_xml(content)
                self.stdout.write(f'   {"✓" if sucesso_xml else "❌"} XML: {msg_xml}')
                if not sucesso_xml:
                    return False
            else:
                ok, decompressed = self._try_decompress(content)
                if not ok:
                    self.stdout.write(f'   ❌ Compressão ZLIB: Falha ao descomprimir ({decompressed})')
                    self.stdout.write("      💡 DICA: Verifique se 'is_zipped' está correto no WebService")
                    return False

                self.stdout.write('   ✓ Compressão ZLIB: OK (descomprimido com sucesso)')
                content_for_parse = decompressed
                sucesso_xml, msg_xml = self.validar_xml(content_for_parse)
                self.stdout.write(f'   {"✓" if sucesso_xml else "❌"} XML: {msg_xml}')
                if not sucesso_xml:
                    return False
        else:
            # is_zipped = False, mas verifica se o conteúdo parece estar compactado
            if self._is_zlib(content):
                self.stdout.write("   ⚠️  Conteúdo PARECE estar compactado, mas 'is_zipped=False'")
                self.stdout.write("      💡 DICA: Ative 'is_zipped=True' no WebService")
                return False

            # Valida XML
            sucesso_xml, msg_xml = self.validar_xml(content)
            self.stdout.write(f'   {"✓" if sucesso_xml else "❌"} XML: {msg_xml}')
            if not sucesso_xml:
                return False

        # Extrai inscrição do XML do edital para usar no teste de candidatos
        if content_for_parse is not None:
            try:
                candidate = self._extract_inscricao_from_edital_xml(content_for_parse)
                if candidate and not self.primer_codigo_candidato:
                    self.primer_codigo_candidato = candidate
                    self.stdout.write(f'   💾 Inscrição encontrada no edital: {self.primer_codigo_candidato}')
            except Exception:
                pass

        return sucesso_http

    def testar_api_candidatos(self):
        """Testa endpoint de importação de candidatos"""
        if not self.webservice.url_candidato:
            self.stdout.write('\n📋 Testando: API de Candidatos - ⊘ NÃO CONFIGURADA')
            return None

        # Usa código real se encontrou, senão usa um padrão
        codigo_candidato = self.primer_codigo_candidato or '00000001'
        self.stdout.write('\n📋 Testando: API de Candidatos')
        if not self.primer_codigo_candidato:
            self.stdout.write('   ⚠️  Não foi possível extrair uma inscrição do edital. Usando 00000001.')
        self.stdout.write(f'   URL padrão: {self.webservice.url_candidato}')

        url = self.webservice.url_candidato.format(self.edital_codigo, codigo_candidato)
        self.stdout.write(f'   URL teste: {url}')

        headers = {'Authorization': f'Token {self.webservice.token or ""}'}

        # Teste DNS
        sucesso_dns, msg_dns = self.testar_dns(url)
        self.stdout.write(f'   {"✓" if sucesso_dns else "❌"} DNS: {msg_dns if msg_dns and not sucesso_dns else "OK"}')
        if not sucesso_dns:
            return False

        # Teste HTTP
        sucesso_http, msg_http, content = self.testar_conectividade(url, headers)
        self.stdout.write(f'   {"✓" if sucesso_http else "❌"} HTTP: {msg_http}')

        if sucesso_http and content:
            # Tenta validar XML se não está compactado
            if isinstance(content, bytes):
                sniff = content[:100].lower()
                has_xml = b'xml' in sniff
            else:
                has_xml = 'xml' in content.lower()[:100]

            if not self.webservice.is_zipped or has_xml:
                try:
                    sucesso_xml, msg_xml = self.validar_xml(content)
                    self.stdout.write(f'   {"✓" if sucesso_xml else "❌"} XML: {msg_xml}')
                except Exception as e:
                    self.stdout.write(f'   ❌ Erro ao validar XML: {e!s}')

        return sucesso_http

    def testar_api_caracterizacoes(self):
        """Testa endpoint de importação de caracterizações"""
        if not self.webservice.url_caracterizacoes:
            self.stdout.write('\n📋 Testando: API de Caracterizações - ⊘ NÃO CONFIGURADA')
            return None

        self.stdout.write('\n📋 Testando: API de Caracterizações')
        self.stdout.write(f'   URL: {self.webservice.url_caracterizacoes}')

        url = self.webservice.url_caracterizacoes.format(self.edital_codigo)

        headers = {'Authorization': f'Token {self.webservice.token or ""}'}

        # Teste DNS
        sucesso_dns, msg_dns = self.testar_dns(url)
        self.stdout.write(f'   {"✓" if sucesso_dns else "❌"} DNS: {msg_dns if msg_dns and not sucesso_dns else "OK"}')
        if not sucesso_dns:
            return False

        # Teste HTTP
        sucesso_http, msg_http, _content = self.testar_conectividade(url, headers)
        self.stdout.write(f'   {"✓" if sucesso_http else "❌"} HTTP: {msg_http}')

        return sucesso_http

    def testar_autenticacao(self):
        """Valida se o token está sendo passado corretamente"""
        self.stdout.write('\n🔐 Testando: Autenticação')

        if not self.webservice.token:
            self.stdout.write('   ⊘ Nenhum token configurado')
            return None

        url = self.webservice.url_editais
        headers_com_token = {'Authorization': f'Token {self.webservice.token}'}
        headers_sem_token = {}

        try:
            import requests

            # Requisição com token
            resp_com = requests.get(url, headers=headers_com_token, timeout=self.timeout)

            # Requisição sem token
            resp_sem = requests.get(url, headers=headers_sem_token, timeout=self.timeout)

            if resp_com.status_code == 200 and resp_sem.status_code != 200:
                self.stdout.write('   ✓ Token requerido e fornecido corretamente')
                return True
            elif resp_com.status_code == 200 and resp_sem.status_code == 200:
                self.stdout.write('   ⊘ Token fornecido mas não parece ser requerido')
                return None
            else:
                self.stdout.write(f'   ❌ Erro ao validar token (com={resp_com.status_code}, sem={resp_sem.status_code})')
                return False
        except Exception as e:
            self.stdout.write(f'   ❌ Erro ao testar autenticação: {e!s}')
            return False

    def executar(self):
        resultados = {
            'Listagem de Editais': self.testar_api_editais(),
            'Edital Específico': self.testar_api_edital(),
            'API de Candidatos': self.testar_api_candidatos(),
            'API de Caracterizações': self.testar_api_caracterizacoes(),
            'Autenticação': self.testar_autenticacao(),
        }

        # Relatório final
        sucessos = sum(1 for v in resultados.values() if v is True)
        total_testados = sum(1 for v in resultados.values() if v is not None)
        taxa_sucesso = (sucessos / total_testados * 100) if total_testados > 0 else 0

        self.stdout.write(f'\n{"=" * 60}')
        self.stdout.write(f'📊 RESUMO: {sucessos}/{total_testados} testes OK ({taxa_sucesso:.0f}%)')
        self.stdout.write(f'{"=" * 60}\n')

        if taxa_sucesso == 100:
            self.stdout.write(self.style.SUCCESS('✓ Todas as APIs estão operacionais!'))
        elif taxa_sucesso >= 50:
            self.stdout.write(self.style.WARNING('⚠️  Algumas APIs com problema. Verificar os erros acima.'))
        else:
            self.stdout.write(self.style.ERROR('❌ Maioria das APIs com problema. Verificar conectividade SGC.'))
