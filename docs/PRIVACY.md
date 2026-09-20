# Auditoria de Privacidade e Processamento Local — Translate_BooK

Este documento detalha os compromissos, garantias arquiteturais e métodos de verificação da privacidade absoluta do **Translate_BooK**.

---

## 1. Princípios Arquiteturais de Privacidade

### 1.1 Processamento 100% Local (Local-First)
- Toda e qualquer operação de tradução, leitura de arquivo, análise de contexto, memória de tradução, QA (Quality Assurance) e exportação é executada **exclusivamente no hardware da sua máquina**.
- Os modelos neurais (MADLAD-400 em formato CTranslate2 quantizado) são executados via bibliotecas locais em C++/Python, utilizando sua CPU ou GPU (CUDA).
- Não há servidores de tradução remota, proxies, ou serviços de IA em nuvem (nem OpenAI, nem Google Cloud, nem Hugging Face Inference API).

### 1.2 Zero Telemetria
- O aplicativo não possui nenhuma biblioteca de telemetria, rastreamento de cliques, Google Analytics, Sentry, Mixpanel ou identificadores persistentes de máquina.
- Nenhuma informação sobre quais livros você abre, quantos parágrafos traduz, ou os erros que ocorrem é enviada para desenvolvedores ou terceiros.

### 1.3 Isolamento dos Dados do Usuário
- Seus livros e suas traduções ficam armazenados localmente no seu computador:
  - **No Windows**: `%APPDATA%\Translate_BooK\projects\<Seu_Projeto>\project.db`
  - **Em Modo Portátil**: `./projects/<Seu_Projeto>/project.db`
- A base de dados SQLite opera com modo WAL (*Write-Ahead Logging*) para proteção contra corrupção em quedas repentinas de energia.
- O desinstalador do Windows **nunca** apaga nem altera a pasta de projetos do usuário.

---

## 2. Medidas de Hardening e Sanitização de Logs

### Sanitização de Informações Pessoais (PII) nos Logs
O sistema inclui um filtro ativo de privacidade (`PrivacySanitizingFilter` em `book_translator.security.audit`):
- Caminhos do sistema operacional que contenham seu nome de usuário (ex: `C:\Users\NomeDoUsuario\...`) são automaticamente substituídos por `[USER_HOME]`.
- Nomes de arquivo e caminhos locais são neutralizados nos logs informativos.
- Parágrafos de livros traduzidos **nunca** são gravados no arquivo de log da aplicação, preservando o sigilo de obras confidenciais ou não publicadas.

---

## 3. Como Verificar e Auditar a Privacidade do Aplicativo

Incentivamos que qualquer usuário ou pesquisador de segurança audite o comportamento do Translate_BooK:

### Método 1: Monitoramento por Firewall
1. Abra o Windows Defender Firewall com Segurança Avançada (ou software como *GlassWire*, *Portmaster* ou *Simplewall*).
2. Adicione uma regra de bloqueio total de saída para `Translate_BooK.exe`.
3. Execute o programa, traduza um livro completo e exporte para EPUB ou DOCX.
4. **Resultado**: O programa funcionará perfeitamente e sem qualquer falha ou aviso, comprovando que nenhuma conexão com a internet é necessária para traduzir.

### Método 2: Inspeção de Pacotes de Rede (Wireshark)
1. Inicie o Wireshark e filtre pelo tráfego de saída da sua máquina.
2. Inicie uma sessão de tradução no Translate_BooK.
3. Observe que zero pacotes são transmitidos durante a tradução, segmentação, QA ou exportação.
*(A única operação de rede permitida é quando você solicita explicitamente o download de um novo modelo de IA na interface do Gerenciador de Modelos, onde a URL é estritamente `https://` com hash SHA-256 verificado).*

---

## 4. Conformidade e Segurança Jurídica

Para tradutores profissionais, editoras e pesquisadores que trabalham sob **acordos de não divulgação (NDAs)**:
- O Translate_BooK atende plenamente aos requisitos de confidencialidade de NDAs rigorosos, pois nenhuma informação digitalizada ou textual trafega por redes públicas ou servidores de IA comerciais.
